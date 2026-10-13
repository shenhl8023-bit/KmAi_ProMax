from __future__ import annotations

import csv
import sys

from part_classification.template_map import (
    TemplateMapError,
    default_map_path,
    default_samples_dir,
    default_templates_dir,
    list_mappings,
    list_templates,
    remove_mapping,
    remove_mappings,
    set_mapping,
    set_mappings,
)

UNSPECIFIED = "（未指定）"
MISSING_TEMPLATE = "（模板缺失）"
MISSING_SAMPLE = "（样本缺失）"


class TemplateMapWindow:
    """样本 → 模板映射的配置窗口。业务规则全部来自 template_map。"""

    def __init__(self, root, *, tk, ttk, filedialog, messagebox) -> None:
        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.rows: list[dict] = []
        root.title("样本 → 模板映射配置")
        root.minsize(720, 420)
        self._build()
        self.refresh()

    def _build(self) -> None:
        tk, ttk = self.tk, self.ttk

        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        self.path_text = tk.StringVar()
        ttk.Label(top, textvariable=self.path_text, justify="left").pack(side="left", anchor="w")
        buttons = ttk.Frame(top)
        buttons.pack(side="right", anchor="n")
        ttk.Button(buttons, text="重新扫描", command=self.refresh).pack(side="left", padx=(0, 4))
        ttk.Button(buttons, text="导出清单…", command=self.export_csv).pack(side="left")

        # 计数是顶部常驻状态文字；底部状态栏只报保存/导出结果与错误，
        # 两者分开，保存提示不会把计数覆盖掉（spec §6）。
        self.count_var = tk.StringVar()
        ttk.Label(self.root, textvariable=self.count_var, padding=(8, 2), anchor="w").pack(fill="x")

        middle = ttk.Frame(self.root, padding=(8, 0))
        middle.pack(fill="both", expand=True)

        left = ttk.Frame(middle)
        left.pack(side="left", fill="both", expand=True)
        self.tree = ttk.Treeview(
            left,
            columns=("sample", "template"),
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("sample", text="样本文件")
        self.tree.heading("template", text="模板文件")
        self.tree.column("sample", width=280, anchor="w")
        self.tree.column("template", width=220, anchor="w")
        self.tree.tag_configure("missing", foreground="#c00000")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        # extended 模式自带 Ctrl 点选与 Shift 连选，但 Ctrl+A 全选未内置。
        self.tree.bind("<Control-a>", self._select_all)
        self.tree.bind("<Control-A>", self._select_all)

        right = ttk.LabelFrame(middle, text="所选样本", padding=8)
        right.pack(side="left", fill="y", padx=(8, 0))
        self.right = right
        ttk.Label(right, text="模板").grid(row=0, column=0, sticky="w")
        self.template_var = tk.StringVar()
        self.template_box = ttk.Combobox(
            right,
            textvariable=self.template_var,
            state="readonly",
            width=30,
        )
        self.template_box.grid(row=1, column=0, sticky="we", pady=(0, 8))
        ttk.Label(right, text="备注").grid(row=2, column=0, sticky="w")
        self.note_var = tk.StringVar()
        self.note_entry = ttk.Entry(right, textvariable=self.note_var, width=32)
        self.note_entry.grid(row=3, column=0, sticky="we", pady=(0, 8))
        self.hint_var = tk.StringVar()
        ttk.Label(right, textvariable=self.hint_var, foreground="#666666", wraplength=220).grid(
            row=4, column=0, sticky="we", pady=(0, 8)
        )
        self.save_button = ttk.Button(right, text="保存", command=self.save)
        self.save_button.grid(row=5, column=0, sticky="we")

        self.status_var = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status_var, padding=(8, 6), anchor="w").pack(fill="x")

    def refresh(self) -> None:
        self.path_text.set(
            f"样本目录：{default_samples_dir()}\n"
            f"模板目录：{default_templates_dir()}\n"
            f"清单文件：{default_map_path()}"
        )
        try:
            self.rows = list_mappings()
            templates = list_templates()
        except TemplateMapError as exc:
            self.rows = []
            templates = []
            self.messagebox.showerror("清单无法读取", f"{exc.code}\n{exc.message}")

        configured = sum(1 for row in self.rows if row["template"])
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(self.rows):
            label = row["template"] or UNSPECIFIED
            tags: tuple[str, ...] = ()
            if not row["sampleExists"]:
                label, tags = MISSING_SAMPLE, ("missing",)
            elif row["template"] and not row["templateExists"]:
                label, tags = MISSING_TEMPLATE, ("missing",)
            self.tree.insert("", "end", iid=str(index), values=(row["sample"], label), tags=tags)

        self.template_box["values"] = [UNSPECIFIED] + [item["name"] for item in templates]
        self.template_var.set(UNSPECIFIED)
        self.note_var.set("")
        self.count_var.set(f"样本 {len(self.rows)} 个，已配置 {configured} 个")

    def _selected_rows(self) -> list[dict]:
        # selection() 返回按显示顺序排列的 iid，可直接映射回 rows。
        return [self.rows[int(iid)] for iid in self.tree.selection()]

    def _select_all(self, _event=None) -> str:
        self.tree.selection_set(self.tree.get_children())
        return "break"

    def _on_select(self, _event=None) -> None:
        rows = self._selected_rows()
        if not rows:
            self.right.configure(text="所选样本")
            self.save_button.configure(text="保存")
            self.hint_var.set("")
            self.note_entry.configure(state="normal")
            return

        if len(rows) == 1:
            # 单条：与批量之前的行为完全一致，可改备注。
            self.right.configure(text="所选样本")
            self.save_button.configure(text="保存")
            self.hint_var.set("")
            self.note_entry.configure(state="normal")
            self.template_var.set(rows[0]["template"] or UNSPECIFIED)
            self.note_var.set(rows[0]["note"])
            return

        # 多条：模板下拉不再假装反映某一行，备注置灰（批量只改模板）。
        self.right.configure(text=f"已选 {len(rows)} 个样本")
        self.save_button.configure(text=f"批量套用（{len(rows)} 个）")
        self.note_entry.configure(state="disabled")
        self.hint_var.set("批量只套用模板，不改动各样本已有的备注。")
        self.note_var.set("")

    def save(self) -> None:
        rows = self._selected_rows()
        if not rows:
            self.status_var.set("请先在左侧选择一个样本")
            return
        chosen = self.template_var.get()
        samples = [row["sample"] for row in rows]
        try:
            if chosen == UNSPECIFIED:
                removed = remove_mappings(samples) if len(samples) > 1 else (
                    [samples[0]] if remove_mapping(samples[0]) else []
                )
            else:
                if len(samples) > 1:
                    # 批量：不改备注（note 留空即保留既有值）
                    set_mappings(samples, chosen)
                else:
                    set_mapping(samples[0], chosen, self.note_var.get())
                removed = None
        except TemplateMapError as exc:
            self.messagebox.showerror("保存失败", f"{exc.code}\n{exc.message}")
            return

        self.refresh()
        if isinstance(removed, list):
            if not removed:
                self.status_var.set("未改动：所选样本本就没有配置模板")
            elif len(removed) == 1:
                self.status_var.set(f"已保存：{removed[0]} → {UNSPECIFIED}")
            else:
                self.status_var.set(f"已批量解除 {len(removed)} 个样本的模板")
        elif len(samples) == 1:
            self.status_var.set(f"已保存：{samples[0]} → {chosen}")
        else:
            self.status_var.set(f"已批量保存 {len(samples)} 个样本 → {chosen}")
    def export_csv(self) -> None:
        target = self.filedialog.asksaveasfilename(
            title="导出映射清单",
            defaultextension=".csv",
            initialfile="样本模板映射.csv",
            filetypes=[("CSV 文件", "*.csv")],
        )
        if not target:
            return
        try:
            with open(target, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["样本文件", "模板文件", "模板是否存在", "备注", "更新时间"])
                for row in self.rows:
                    writer.writerow(
                        [
                            row["sample"],
                            row["template"] or "",
                            "是" if row["templateExists"] else "否",
                            row["note"],
                            row["updatedAt"],
                        ]
                    )
        except OSError as exc:
            self.messagebox.showerror("导出失败", str(exc))
            return
        self.status_var.set(f"已导出 {len(self.rows)} 行到 {target}")


def main(argv: list[str] | None = None) -> int:
    # tkinter 在无显示器或未安装 Tk 的机器上不可用，给出明确提示而不是裸回溯。
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        print(f"无法启动界面：当前 Python 缺少 tkinter（{exc}）", file=sys.stderr)
        return 1
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"无法启动界面：没有可用的图形显示（{exc}）", file=sys.stderr)
        return 1
    TemplateMapWindow(
        root,
        tk=tk,
        ttk=ttk,
        filedialog=filedialog,
        messagebox=messagebox,
    )
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
