import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import socket
import time
import os
import queue


class TurboSenderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Sender")
        self.root.geometry("920x760")
        self.root.minsize(860, 650)

        self.running = False

        self.stats_lock = threading.Lock()
        self.work_lock = threading.Lock()

        self.log_queue = queue.SimpleQueue()

        self.sent_packets = 0
        self.sent_bytes = 0
        self.errors = 0
        self.last_packets = 0
        self.last_bytes = 0

        self.cursor = 0
        self.workers_alive = 0

        self.host = ""
        self.ip = ""
        self.port = 0
        self.proto = "UDP"
        self.mode = "LOOP"
        self.threads = 1
        self.delay = 0.0
        self.lines = []

        self.separator = b"\n"

        self.addr = None

        self.build_ui()
        self.create_context_menus()

        self.root.after(100, self.flush_logs)
        self.root.after(1000, self.update_stats)

    # =========================
    # UI
    # =========================
    def build_ui(self):
        pad = {"padx": 8, "pady": 4}

        frame = tk.Frame(self.root)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Host").grid(row=0, column=0, sticky="w", **pad)
        self.entry_host = tk.Entry(frame)
        self.entry_host.grid(row=0, column=1, sticky="ew", **pad)

        tk.Label(frame, text="Port").grid(row=1, column=0, sticky="w", **pad)
        self.entry_port = tk.Entry(frame)
        self.entry_port.grid(row=1, column=1, sticky="ew", **pad)

        tk.Label(frame, text="Protocol").grid(row=2, column=0, sticky="w", **pad)
        self.proto_var = tk.StringVar(value="UDP")

        ttk.Combobox(
            frame,
            textvariable=self.proto_var,
            values=("UDP", "TCP"),
            state="readonly"
        ).grid(row=2, column=1, sticky="ew", **pad)

        tk.Label(frame, text="Threads").grid(row=3, column=0, sticky="w", **pad)

        self.entry_threads = tk.Entry(frame)
        self.entry_threads.insert(0, "1")
        self.entry_threads.grid(row=3, column=1, sticky="ew", **pad)

        tk.Label(frame, text="Delay ms").grid(row=4, column=0, sticky="w", **pad)

        self.entry_delay = tk.Entry(frame)
        self.entry_delay.insert(0, "0")
        self.entry_delay.grid(row=4, column=1, sticky="ew", **pad)

        tk.Label(frame, text="Separator").grid(row=5, column=0, sticky="w", **pad)

        self.entry_separator = tk.Entry(frame)
        self.entry_separator.insert(0, "\\n")
        self.entry_separator.grid(row=5, column=1, sticky="ew", **pad)

        tk.Label(frame, text="Mode").grid(row=6, column=0, sticky="w", **pad)

        modef = tk.Frame(frame)
        modef.grid(row=6, column=1, sticky="w", **pad)

        self.mode_var = tk.StringVar(value="LOOP")

        tk.Radiobutton(
            modef,
            text="Once",
            variable=self.mode_var,
            value="ONCE"
        ).pack(side="left")

        tk.Radiobutton(
            modef,
            text="Loop",
            variable=self.mode_var,
            value="LOOP"
        ).pack(side="left")

        tk.Label(frame, text="Source").grid(row=7, column=0, sticky="w", **pad)

        srcf = tk.Frame(frame)
        srcf.grid(row=7, column=1, sticky="w", **pad)

        self.source_var = tk.StringVar(value="TEXT")

        tk.Radiobutton(
            srcf,
            text="Text",
            variable=self.source_var,
            value="TEXT"
        ).pack(side="left")

        tk.Radiobutton(
            srcf,
            text="File",
            variable=self.source_var,
            value="FILE"
        ).pack(side="left")

        tk.Label(frame, text="Text").grid(row=8, column=0, sticky="nw", **pad)

        self.text_input = tk.Text(frame, height=8)
        self.text_input.grid(row=8, column=1, sticky="nsew", **pad)

        tk.Label(frame, text="File").grid(row=9, column=0, sticky="w", **pad)

        ff = tk.Frame(frame)
        ff.grid(row=9, column=1, sticky="ew", **pad)

        self.file_var = tk.StringVar()

        tk.Entry(
            ff,
            textvariable=self.file_var
        ).pack(side="left", fill="x", expand=True)

        tk.Button(
            ff,
            text="Browse",
            command=self.select_file
        ).pack(side="left")

        bf = tk.Frame(frame)
        bf.grid(row=10, column=0, columnspan=2, sticky="ew", **pad)

        tk.Button(
            bf,
            text="Start",
            width=18,
            command=self.start_send
        ).pack(side="left", padx=3)

        tk.Button(
            bf,
            text="Stop",
            width=18,
            command=self.stop_send
        ).pack(side="left", padx=3)

        tk.Button(
            bf,
            text="Clear Log",
            width=18,
            command=self.clear_log
        ).pack(side="left", padx=3)

        stats = tk.LabelFrame(frame, text="Statistics")
        stats.grid(row=11, column=0, columnspan=2, sticky="ew", padx=8, pady=8)

        self.lbl_pps = tk.Label(stats, text="PPS: 0")
        self.lbl_pps.pack(anchor="w")

        self.lbl_mbps = tk.Label(stats, text="Mbps: 0")
        self.lbl_mbps.pack(anchor="w")

        self.lbl_total = tk.Label(stats, text="Packets: 0")
        self.lbl_total.pack(anchor="w")

        self.lbl_err = tk.Label(stats, text="Errors: 0")
        self.lbl_err.pack(anchor="w")

        tk.Label(frame, text="Log").grid(row=12, column=0, sticky="nw", **pad)

        self.log_box = tk.Text(frame, height=18)
        self.log_box.grid(row=12, column=1, sticky="nsew", **pad)

        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(12, weight=1)

    # =========================
    # Context menu
    # =========================
    def create_context_menus(self):
        self.context_widget = None

        self.menu = tk.Menu(self.root, tearoff=0)

        self.menu.add_command(
            label="Cut",
            command=lambda: self.context_widget.event_generate("<<Cut>>")
        )

        self.menu.add_command(
            label="Copy",
            command=lambda: self.context_widget.event_generate("<<Copy>>")
        )

        self.menu.add_command(
            label="Paste",
            command=lambda: self.context_widget.event_generate("<<Paste>>")
        )

        self.menu.add_separator()

        self.menu.add_command(
            label="Select All",
            command=self.select_all
        )

        widgets = (
            self.entry_host,
            self.entry_port,
            self.entry_threads,
            self.entry_delay,
            self.entry_separator,
            self.text_input,
            self.log_box
        )

        for w in widgets:
            w.bind("<Button-3>", self.show_menu)
            w.bind("<Control-a>", self.ctrl_a)
            w.bind("<Control-A>", self.ctrl_a)

    def show_menu(self, event):
        self.context_widget = event.widget
        self.menu.tk_popup(event.x_root, event.y_root)

    def ctrl_a(self, event):
        self.context_widget = event.widget
        self.select_all()
        return "break"

    def select_all(self):
        try:
            self.context_widget.tag_add("sel", "1.0", "end")
        except Exception:
            self.context_widget.select_range(0, "end")

    # =========================
    # Logging
    # =========================
    def log(self, msg):
        self.log_queue.put(msg)

    def flush_logs(self):
        insert = self.log_box.insert
        end = tk.END
        now = time.strftime

        count = 0

        while count < 300:
            try:
                msg = self.log_queue.get_nowait()
            except Exception:
                break

            insert(end, f"[{now('%H:%M:%S')}] {msg}\n")
            count += 1

        if count:
            line_count = int(
                self.log_box.index("end-1c").split(".")[0]
            )

            if line_count > 1000:
                self.log_box.delete("1.0", "300.0")

            self.log_box.see(end)

        self.root.after(100, self.flush_logs)

    # =========================
    # Stats
    # =========================
    def update_stats(self):
        with self.stats_lock:
            packets = self.sent_packets
            total_bytes = self.sent_bytes
            errors = self.errors

            pps = packets - self.last_packets
            bps = total_bytes - self.last_bytes

            self.last_packets = packets
            self.last_bytes = total_bytes

        self.lbl_pps.config(text=f"PPS: {pps}")
        self.lbl_mbps.config(
            text=f"Mbps: {(bps * 8) / 1_000_000:.2f}"
        )
        self.lbl_total.config(text=f"Packets: {packets}")
        self.lbl_err.config(text=f"Errors: {errors}")

        self.root.after(1000, self.update_stats)

    # =========================
    # Helpers
    # =========================
    def clear_log(self):
        self.log_box.delete("1.0", tk.END)

    def select_file(self):
        path = filedialog.askopenfilename()

        if path:
            self.file_var.set(path)

    def load_lines(self):
        result = []

        if self.source_var.get() == "FILE":
            path = self.file_var.get().strip()

            if not os.path.isfile(path):
                raise ValueError("File not found")

            with open(path, "rb") as f:
                for line in f:
                    line = line.rstrip(b"\r\n")

                    if line:
                        result.append(line + self.separator)

        else:
            txt = self.text_input.get("1.0", tk.END).splitlines()

            for x in txt:
                x = x.strip()

                if x:
                    result.append(
                        x.encode("utf-8") + self.separator
                    )

        return result

    # =========================
    # Start / Stop
    # =========================
    def start_send(self):
        if self.running:
            return

        try:
            self.host = self.entry_host.get().strip()
            self.ip = socket.gethostbyname(self.host)

            self.port = int(
                self.entry_port.get().strip()
            )

            self.proto = self.proto_var.get()
            self.mode = self.mode_var.get()

            self.threads = max(
                1,
                min(256, int(self.entry_threads.get().strip()))
            )

            self.delay = (
                float(self.entry_delay.get().strip()) / 1000.0
            )

            sep = self.entry_separator.get()

            self.separator = (
                sep
                .encode("utf-8")
                .decode("unicode_escape")
                .encode("utf-8")
            )

            self.lines = self.load_lines()

            if not self.lines:
                raise ValueError("No data")

            self.addr = (self.ip, self.port)

            self.sent_packets = 0
            self.sent_bytes = 0
            self.errors = 0

            self.last_packets = 0
            self.last_bytes = 0

            self.cursor = 0
            self.workers_alive = self.threads

            self.running = True

            for i in range(self.threads):
                threading.Thread(
                    target=self.worker,
                    args=(i + 1,),
                    daemon=True
                ).start()

            self.log(
                f"Started {self.proto} "
                f"{self.mode} "
                f"{self.threads} threads"
            )

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def stop_send(self):
        self.running = False
        self.log("Stop requested")

    # =========================
    # Fast line allocator
    # =========================
    def get_next_line(self):
        with self.work_lock:
            idx = self.cursor
            self.cursor += 1

            if self.mode == "ONCE":
                if idx >= len(self.lines):
                    return None

                return self.lines[idx]

            return self.lines[idx % len(self.lines)]

    # =========================
    # Network
    # =========================
    def open_socket(self):
        if self.proto == "UDP":
            return socket.socket(
                socket.AF_INET,
                socket.SOCK_DGRAM
            )

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        sock.settimeout(5)
        sock.connect(self.addr)

        return sock

    # =========================
    # Worker
    # =========================
    def worker(self, tid):
        sock = None
        count = 0

        proto_udp = self.proto == "UDP"
        delay = self.delay
        running_ref = self

        try:
            sock = self.open_socket()

            if proto_udp:
                send = sock.sendto
                addr = self.addr
            else:
                send = sock.sendall

            while running_ref.running:
                data = self.get_next_line()

                if data is None:
                    break

                try:
                    if proto_udp:
                        send(data, addr)
                    else:
                        send(data)

                    with self.stats_lock:
                        self.sent_packets += 1
                        self.sent_bytes += len(data)

                except Exception:
                    with self.stats_lock:
                        self.errors += 1

                    if not proto_udp:
                        try:
                            sock.close()
                        except Exception:
                            pass

                        sock = self.open_socket()
                        send = sock.sendall

                count += 1

                if count % 5000 == 0:
                    self.log(f"T{tid}: {count}")

                if delay:
                    time.sleep(delay)

        except Exception as e:
            self.log(f"T{tid} ERROR: {e}")

        finally:
            try:
                if sock:
                    sock.close()
            except Exception:
                pass

            with self.work_lock:
                self.workers_alive -= 1

                if self.workers_alive <= 0:
                    self.running = False
                    self.log("Finished")


if __name__ == "__main__":
    root = tk.Tk()
    app = TurboSenderApp(root)
    root.mainloop()