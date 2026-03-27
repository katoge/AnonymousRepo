import tkinter as tk
from tkinterdnd2 import DND_FILES, TkinterDnD
import json
import os

def parse_jsonl(file_path):
    data = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                item = json.loads(line.strip())
                if 'source_file' in item:
                    data[item['source_file']] = {
                        'compilable': item.get('compilable', 0),
                        'pass': item.get('pass', 0)
                    }
            except json.JSONDecodeError:
                continue
    return data

def compute_hamming(dict1, dict2):
    matched_keys = set(dict1.keys()) & set(dict2.keys())
    total = len(matched_keys)

    if total == 0:
        return 0, 0, 0, 0, []  # no common keys

    hamming_compile = 0
    hamming_pass = 0
    mismatches = []

    for k in matched_keys:
        c1 = dict1[k]['compilable']
        c2 = dict2[k]['compilable']
        p1 = dict1[k]['pass']
        p2 = dict2[k]['pass']

        diff_compile = c1 != c2
        diff_pass = p1 != p2

        if diff_compile:
            hamming_compile += 1
        if diff_pass:
            hamming_pass += 1

        if diff_compile or diff_pass:
            mismatches.append(f"{k}  (compilable: {c1} vs {c2}, pass: {p1} vs {p2})")

    norm_compile = hamming_compile / total
    norm_pass = hamming_pass / total

    return hamming_compile, norm_compile, hamming_pass, norm_pass, mismatches

class HammingApp:
    def __init__(self, root):
        self.root = root
        self.root.attributes("-topmost", True)
        self.root.minsize(600, 300) 
        self.root.title("JSONL Hamming Distance Comparator")
        self.file1 = None
        self.file2 = None

        self.label1 = tk.Label(root, text="Drop first JSONL file here", width=90, height=3, relief="ridge")
        self.label1.pack(pady=10)
        self.label1.drop_target_register(DND_FILES)
        self.label1.dnd_bind('<<Drop>>', self.drop_file1)

        self.label2 = tk.Label(root, text="Drop second JSONL file here", width=90, height=3, relief="ridge")
        self.label2.pack(pady=10)
        self.label2.drop_target_register(DND_FILES)
        self.label2.dnd_bind('<<Drop>>', self.drop_file2)

        self.result_label = tk.Label(root, text="", justify="left", font=("Courier", 12))
        self.result_label.pack(pady=10)

        self.mismatch_label = tk.Label(root, text="Mismatched Lines:")
        self.mismatch_label.pack(pady=(10, 0))

        self.text_frame = tk.Frame(root)
        self.text_frame.pack(pady=5, fill="both", expand=True)

        self.text_scroll = tk.Scrollbar(self.text_frame)
        self.text_scroll.pack(side="right", fill="y")

        self.sync_button = tk.Button(root, text="Synchronize", command=self.try_compute)
        self.sync_button.pack(pady=10)


        self.mismatch_text = tk.Text(self.text_frame, height=12, wrap="none", yscrollcommand=self.text_scroll.set)
        self.mismatch_text.pack(side="left", fill="both", expand=True)
        self.text_scroll.config(command=self.mismatch_text.yview)
    def pretty_path(self, full_path):
        parts = full_path.strip(os.sep).split(os.sep)
        last_parts = parts[-3:] if len(parts) >= 3 else parts
        return os.path.join(*last_parts)

    def drop_file1(self, event):
        self.file1 = event.data.strip('{}')
        self.label1.config(text=self.pretty_path(self.file1))
        self.try_compute()

    def drop_file2(self, event):
        self.file2 = event.data.strip('{}')
        self.label2.config(text=self.pretty_path(self.file2))
        self.try_compute()

    def try_compute(self):
        if self.file1 and self.file2:
            self.mismatch_text.config(state="normal")
            dict1 = parse_jsonl(self.file1)
            dict2 = parse_jsonl(self.file2)

            def average_metrics(data, label):
                total = len(data)
                if total == 0:
                    print(f"{label}: No data.")
                    return
                total_compile = sum(1 for v in data.values() if v['compilable'] == 1)
                total_pass = sum(1 for v in data.values() if v['pass'] == 1)
                avg_compile = total_compile / total
                avg_pass = total_pass / total
                print(f"{label} - Total: {total}")
                print(f"  Average Compilable Ratio: {avg_compile:.4f}")
                print(f"  Average Pass Ratio: {avg_pass:.4f}")

            average_metrics(dict1, "File 1")
            average_metrics(dict2, "File 2")
            h_compile, norm_compile, h_pass, norm_pass, mismatches = compute_hamming(dict1, dict2)

            # Track mismatch types
            compile_0_to_1 = compile_1_to_0 = pass_0_to_1 = pass_1_to_0 = 0

            matched_keys = set(dict1.keys()) & set(dict2.keys())
            for k in matched_keys:
                c1, c2 = dict1[k]['compilable'], dict2[k]['compilable']
                p1, p2 = dict1[k]['pass'], dict2[k]['pass']

                if c1 != c2:
                    if c1 == 0 and c2 == 1:
                        compile_0_to_1 += 1
                    elif c1 == 1 and c2 == 0:
                        compile_1_to_0 += 1
                
                if p1 != p2:
                    if p1 == 0 and p2 == 1:
                        pass_0_to_1 += 1
                    elif p1 == 1 and p2 == 0:
                        pass_1_to_0 += 1

            def format_ratio(label, one_to_zero, zero_to_one):
                total = one_to_zero + zero_to_one
                if total == 0:
                    return f"{label} Ratio: No mismatches"
                pct_1_0 = (one_to_zero / total) * 100
                pct_0_1 = (zero_to_one / total) * 100
                return (f"{label} Ratio:\n"
                        f"1 vs 0: {one_to_zero} ({pct_1_0:.2f}%)\n"
                        f"0 vs 1: {zero_to_one} ({pct_0_1:.2f}%)")

            compile_ratio = format_ratio("Compilable", compile_1_to_0, compile_0_to_1)
            pass_ratio = format_ratio("Pass", pass_1_to_0, pass_0_to_1)

            result = (
                f"Hamming Distance Compilable: {h_compile}\n"
                f"Normalized Hamming Distance Compilable: {norm_compile:.4f}\n\n"
                f"Hamming Distance Pass: {h_pass}\n"
                f"Normalized Hamming Distance Pass: {norm_pass:.4f}\n\n"
                f"{compile_ratio}\n\n{pass_ratio}"
            )

            self.result_label.config(text=result)

            self.mismatch_text.delete(1.0, tk.END)
            if mismatches:
                self.mismatch_text.insert(tk.END, "\n".join(mismatches))
            else:
                self.mismatch_text.insert(tk.END, "No mismatches found.")
            self.mismatch_text.config(state="disabled")
            self.mismatch_text.bind("<1>", lambda e: self.mismatch_text.focus_set())
            self.mismatch_text.bind("<Control-c>", lambda e: self.copy_selection())

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    window_width = 800
    window_height = 600

    # Get screen width and height
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    # Calculate center coordinates
    x = (screen_width // 2) - (window_width // 2)
    y = (screen_height // 2) - (window_height // 2)

    # Set geometry and min size
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    app = HammingApp(root)
    root.mainloop()
