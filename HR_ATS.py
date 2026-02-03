import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog, filedialog
import sqlite3
import datetime
import csv
import webbrowser
from urllib.parse import quote
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

# =========================
# CONFIG
# =========================
DB_FILE = "hr_ats.db"

STAGES = [
    "Applied", "Screening", "Interview", "Background Check",
    "Offer", "Hired", "Rejected"
]

JOB_BOARDS = [
    {"name": "Indeed",       "key_prefix": "indeed",     "needs_api_key": True,  "needs_oauth": False},
    {"name": "ZipRecruiter", "key_prefix": "ziprecruiter", "needs_api_key": True,  "needs_oauth": False},
    {"name": "LinkedIn",     "key_prefix": "linkedin",   "needs_api_key": False, "needs_oauth": True},
    {"name": "Monster",      "key_prefix": "monster",    "needs_api_key": True,  "needs_oauth": False},
]

# =========================
# DATABASE
# =========================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.migrate()
        self.create_tables()
        self.seed()

    def migrate(self):
        c = self.conn.cursor()

        # ── applicants table migration ───────────────────────────────────────
        c.execute("PRAGMA table_info(applicants)")
        cols = {r[1] for r in c.fetchall()}

        # Add missing columns
        migrations = [
            ("interview_date", "TEXT"),
            ("applied_date", "TEXT"),
            ("hired_date", "TEXT"),
            ("notes", "TEXT"),
            ("source", "TEXT DEFAULT 'Manual'"),   # ← this was missing
        ]

        for col_name, col_type in migrations:
            if col_name not in cols:
                try:
                    c.execute(f"ALTER TABLE applicants ADD COLUMN {col_name} {col_type}")
                    print(f"Added column: {col_name}")
                except sqlite3.OperationalError as e:
                    print(f"Could not add column {col_name}: {e}")

        # If source was just added, set default value for old rows
        if "source" not in cols:
            c.execute("UPDATE applicants SET source = 'Manual' WHERE source IS NULL")

        # ── email_templates migration ───────────────────────────────────────
        c.execute("PRAGMA table_info(email_templates)")
        tcols = {r[1] for r in c.fetchall()}
        if "name" not in tcols and "id" in tcols:
            c.execute("ALTER TABLE email_templates ADD COLUMN name TEXT")
            c.execute("UPDATE email_templates SET name = 'Template ' || id WHERE name IS NULL OR name = ''")

        # ── settings table ──────────────────────────────────────────────────
        c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        self.conn.commit()

    def create_tables(self):
        c = self.conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS applicants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            job TEXT,
            status TEXT,
            notes TEXT,
            interview_date TEXT,
            applied_date TEXT,
            hired_date TEXT,
            source TEXT DEFAULT 'Manual'
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            applicant_id INTEGER,
            date TEXT,
            change TEXT,
            FOREIGN KEY(applicant_id) REFERENCES applicants(id) ON DELETE CASCADE
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS email_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            subject TEXT,
            body TEXT
        )
        """)
        self.conn.commit()

    def seed(self):
        c = self.conn.cursor()
        if c.execute("SELECT COUNT(*) FROM email_templates").fetchone()[0] == 0:
            c.executemany("""
                INSERT INTO email_templates (name, subject, body) VALUES (?,?,?)
            """, [
                ("Interview Invite", "Interview Invitation – {job}",
                 "Hi {name},\n\nWe would like to invite you to interview for the {job} position.\n\nBest regards,\nHR Team"),
                ("Offer Sent", "Job Offer – {job}",
                 "Dear {name},\n\nCongratulations! We are pleased to offer you the {job} position.\n\nHR Team"),
                ("Rejection", "Application Update",
                 "Dear {name},\n\nThank you for your interest in the {job} position.\n\nWe have decided to move forward with other candidates.\n\nBest wishes,\nHR Team")
            ])
        self.conn.commit()

    def get_setting(self, key, default=None):
        c = self.conn.cursor()
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key, value):
        c = self.conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, str(value)))
        self.conn.commit()


db = Database()


# =========================
# MAIN APPLICATION
# =========================
class HRApp:
    def __init__(self, root):
        self.root = root
        root.title("HR ATS")
        root.geometry("1280x820")
        root.minsize(1100, 700)

        self.style_ui()
        self.build_ui()
        self.refresh_all()

    def style_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", font=("Segoe UI", 10), padding=8)
        style.map("TButton", background=[("active", "#1d4ed8")])
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=28)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    def build_ui(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=12, pady=12)

        self.tab_dashboard   = ttk.Frame(self.nb)
        self.tab_applicants  = ttk.Frame(self.nb)
        self.tab_templates   = ttk.Frame(self.nb)
        self.tab_settings    = ttk.Frame(self.nb)

        self.nb.add(self.tab_dashboard,   text="Dashboard")
        self.nb.add(self.tab_applicants,  text="Applicants")
        self.nb.add(self.tab_templates,   text="Email Templates")
        self.nb.add(self.tab_settings,    text="Settings")

        self.build_dashboard()
        self.build_applicants_tab()
        self.build_templates_tab()
        self.build_settings_tab()

    # ────────────────────────────────────────────────
    #  DASHBOARD
    # ────────────────────────────────────────────────
    def build_dashboard(self):
        f = ttk.Frame(self.tab_dashboard, padding=20)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Dashboard", font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(0,16))

        stats = ttk.Frame(f)
        stats.pack(fill="x", pady=10)

        self.lbl_total   = ttk.Label(stats, text="Total Applicants: —", font=("Segoe UI", 12))
        self.lbl_total.pack(side="left", padx=20)

        self.lbl_status  = ttk.Label(stats, text="Statuses: —", font=("Segoe UI", 12))
        self.lbl_status.pack(side="left", padx=20)

        upcoming = ttk.LabelFrame(f, text="Upcoming Interviews (next 7 days)", padding=12)
        upcoming.pack(fill="x", pady=12)

        self.upcoming_text = scrolledtext.ScrolledText(upcoming, height=5, state="disabled", font=("Segoe UI", 10))
        self.upcoming_text.pack(fill="both", expand=True)

        recent = ttk.LabelFrame(f, text="Recently Added (last 7 days)", padding=12)
        recent.pack(fill="both", expand=True)

        cols = ("Name", "Job", "Source", "Applied")
        self.recent_tree = ttk.Treeview(recent, columns=cols, show="headings", height=8)
        for c in cols:
            self.recent_tree.heading(c, text=c)
            self.recent_tree.column(c, width=140 if c != "Applied" else 100)
        self.recent_tree.pack(fill="both", expand=True)

    def refresh_dashboard(self):
        c = db.conn.cursor()
        today = datetime.date.today()

        total = c.execute("SELECT COUNT(*) FROM applicants").fetchone()[0]
        self.lbl_total.config(text=f"Total Applicants: {total}")

        status_data = c.execute("SELECT status, COUNT(*) FROM applicants GROUP BY status").fetchall()
        status_str = "  •  ".join(f"{k}: {v}" for k,v in status_data if k)
        self.lbl_status.config(text=f"Statuses: {status_str or '—'}")

        next7 = today + datetime.timedelta(days=7)
        rows = c.execute("""
            SELECT name, job, interview_date FROM applicants
            WHERE interview_date >= ? AND interview_date <= ?
            ORDER BY interview_date
        """, (str(today), str(next7))).fetchall()

        self.upcoming_text.config(state="normal")
        self.upcoming_text.delete("1.0", tk.END)
        if not rows:
            self.upcoming_text.insert("end", "No upcoming interviews.\n")
        else:
            for n, j, d in rows:
                self.upcoming_text.insert("end", f"{d}   {n}  ({j})\n")
        self.upcoming_text.config(state="disabled")

        last7 = today - datetime.timedelta(days=7)
        for item in self.recent_tree.get_children():
            self.recent_tree.delete(item)

        c.execute("""
            SELECT name, job, source, applied_date FROM applicants
            WHERE applied_date >= ?
            ORDER BY applied_date DESC LIMIT 12
        """, (str(last7),))

        for n, j, src, d in c.fetchall():
            self.recent_tree.insert("", "end", values=(n, j, src or "Manual", d))

    # ────────────────────────────────────────────────
    #  APPLICANTS TAB
    # ────────────────────────────────────────────────
    def build_applicants_tab(self):
        f = ttk.Frame(self.tab_applicants, padding=15)
        f.pack(fill="both", expand=True)

        cols = ("Name", "Email", "Job", "Status", "Source", "Interview")
        self.tree = ttk.Treeview(f, columns=cols, show="headings")
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=10)

        btns = ttk.Frame(f)
        btns.pack(fill="x", pady=8)

        ttk.Button(btns, text="➕ Add Applicant", command=self.add_applicant).pack(side="left", padx=4)
        ttk.Button(btns, text="📥 Import CSV", command=self.import_csv).pack(side="left", padx=4)
        ttk.Button(btns, text="🌐 Import from Job Boards", command=self.import_from_integrations).pack(side="left", padx=4)
        ttk.Button(btns, text="✏️ Update Status", command=self.update_status).pack(side="left", padx=4)
        ttk.Button(btns, text="📅 Interview Date", command=self.set_interview_date).pack(side="left", padx=4)
        ttk.Button(btns, text="✉️ Send Email", command=self.send_email).pack(side="left", padx=4)
        ttk.Button(btns, text="📄 Offer PDF", command=self.generate_offer_pdf).pack(side="left", padx=4)
        ttk.Button(btns, text="🗑️ Delete", command=self.delete_applicant).pack(side="right", padx=4)

    def refresh_applicants(self):
        self.tree.delete(*self.tree.get_children())
        c = db.conn.cursor()
        c.execute("""
            SELECT id, name, email, job, status, source, interview_date 
            FROM applicants 
            ORDER BY applied_date DESC
        """)
        for row in c.fetchall():
            values = list(row[1:])
            values[4] = values[4] or "Manual"  # source
            self.tree.insert("", "end", iid=row[0], values=values)

    def add_applicant(self):
        win = tk.Toplevel(self.root)
        win.title("Add Applicant")
        win.geometry("460x440")

        fields = {}
        for i, lbl in enumerate(["Name*", "Email*", "Phone", "Job", "Applied Date (YYYY-MM-DD)", "Source", "Notes"]):
            ttk.Label(win, text=lbl).grid(row=i, column=0, padx=12, pady=8, sticky="e")
            if lbl == "Notes":
                w = scrolledtext.ScrolledText(win, width=40, height=5)
            else:
                w = ttk.Entry(win, width=40)
            w.grid(row=i, column=1, padx=8, pady=4, sticky="ew")
            fields[lbl.rstrip("*")] = w

        def save():
            name = fields["Name"].get().strip()
            email = fields["Email"].get().strip()
            if not name or not email:
                messagebox.showwarning("Required", "Name and Email are required.")
                return

            applied = fields.get("Applied Date", "").get().strip() or str(datetime.date.today())
            source = fields.get("Source", "").get().strip() or "Manual"

            c = db.conn.cursor()
            c.execute("""
                INSERT INTO applicants (name, email, phone, job, status, applied_date, source, notes)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                name, email,
                fields["Phone"].get().strip(),
                fields["Job"].get().strip(),
                "Applied",
                applied,
                source,
                fields["Notes"].get("1.0", tk.END).strip() if "Notes" in fields else ""
            ))
            app_id = c.lastrowid
            c.execute("INSERT INTO history (applicant_id, date, change) VALUES (?,?,?)",
                      (app_id, str(datetime.date.today()), "Added manually"))
            db.conn.commit()
            win.destroy()
            self.refresh_all()

        ttk.Button(win, text="Save", command=save).grid(row=7, column=0, columnspan=2, pady=20)

    def import_csv(self):
        file = filedialog.askopenfilename(
            title="Select CSV file",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not file:
            return

        try:
            with open(file, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = [h.lower() for h in (reader.fieldnames or [])]

                name_idx  = next((i for i, h in enumerate(fieldnames) if "name" in h), None)
                email_idx = next((i for i, h in enumerate(fieldnames) if "email" in h), None)
                phone_idx = next((i for i, h in enumerate(fieldnames) if "phone" in h), None)
                job_idx   = next((i for i, h in enumerate(fieldnames) if "job" in h or "title" in h), None)
                date_idx  = next((i for i, h in enumerate(fieldnames) if "date" in h or "applied" in h), None)

                c = db.conn.cursor()
                added = 0

                for row in reader:
                    values = list(row.values())
                    name  = (values[name_idx] if name_idx is not None else "").strip()
                    email = (values[email_idx] if email_idx is not None else "").strip()
                    if not name or not email:
                        continue

                    c.execute("""
                        INSERT OR IGNORE INTO applicants
                        (name, email, phone, job, status, applied_date, source)
                        VALUES (?,?,?,?,?,?,?)
                    """, (
                        name,
                        email,
                        values[phone_idx] if phone_idx is not None else "",
                        values[job_idx] if job_idx is not None else "",
                        "Applied",
                        values[date_idx] if date_idx is not None else str(datetime.date.today()),
                        "CSV Import"
                    ))
                    if c.rowcount > 0:
                        added += 1

                db.conn.commit()
                messagebox.showinfo("Import Complete", f"Imported {added} new applicants.\n(duplicates skipped)")
                self.refresh_all()

        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to import CSV:\n{str(e)}")

    def import_from_integrations(self):
        messagebox.showinfo(
            "Integrations",
            "Automatic import from job boards is not yet implemented.\n\n"
            "Configure connections in Settings → Job Board Integrations.\n"
            "Use CSV import for now."
        )

    def delete_applicant(self):
        sel = self.tree.selection()
        if not sel:
            return
        if not messagebox.askyesno("Delete", "Delete selected applicant?"):
            return
        c = db.conn.cursor()
        c.execute("DELETE FROM applicants WHERE id=?", (sel[0],))
        db.conn.commit()
        self.refresh_all()

    def update_status(self):
        sel = self.tree.selection()
        if not sel: return
        app_id = sel[0]

        win = tk.Toplevel(self.root)
        win.title("Update Status")
        combo = ttk.Combobox(win, values=STAGES, state="readonly", width=30)
        combo.current(0)
        combo.pack(padx=30, pady=20)

        def save():
            status = combo.get()
            c = db.conn.cursor()
            c.execute("UPDATE applicants SET status=? WHERE id=?", (status, app_id))
            c.execute("INSERT INTO history (applicant_id, date, change) VALUES (?,?,?)",
                      (app_id, str(datetime.date.today()), f"Status → {status}"))
            db.conn.commit()
            win.destroy()
            self.refresh_all()

        ttk.Button(win, text="Update", command=save).pack(pady=10)

    def set_interview_date(self):
        sel = self.tree.selection()
        if not sel: return
        app_id = sel[0]

        date = simpledialog.askstring("Interview Date", "YYYY-MM-DD", parent=self.root)
        if not date: return

        c = db.conn.cursor()
        c.execute("UPDATE applicants SET interview_date=? WHERE id=?", (date.strip(), app_id))
        c.execute("INSERT INTO history (applicant_id, date, change) VALUES (?,?,?)",
                  (app_id, str(datetime.date.today()), f"Interview: {date}"))
        db.conn.commit()
        self.refresh_all()

    def send_email(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select an applicant first.")
            return

        app_id = sel[0]
        c = db.conn.cursor()
        c.execute("SELECT name, email, job FROM applicants WHERE id=?", (app_id,))
        name, email, job = c.fetchone() or (None, None, None)

        if not email:
            messagebox.showwarning("No Email", "Applicant has no email address.")
            return

        c.execute("SELECT name, subject, body FROM email_templates ORDER BY name")
        templates = c.fetchall()

        if not templates:
            messagebox.showinfo("No Templates", "No email templates found.")
            return

        win = tk.Toplevel(self.root)
        win.title("Choose Template")

        ttk.Label(win, text="Select email template:").pack(pady=10, padx=20)

        lb = tk.Listbox(win, width=50, height=10)
        lb.pack(padx=20, pady=5, fill="both")
        for t in templates:
            lb.insert(tk.END, t[0])

        def send():
            idx = lb.curselection()
            if not idx: return
            subj = templates[idx[0]][1].replace("{name}", name or "").replace("{job}", job or "")
            body = templates[idx[0]][2].replace("{name}", name or "").replace("{job}", job or "")

            url = f"mailto:{email}?subject={quote(subj)}&body={quote(body)}"
            webbrowser.open(url)
            win.destroy()

        ttk.Button(win, text="Send", command=send).pack(pady=15)

    def generate_offer_pdf(self):
        sel = self.tree.selection()
        if not sel: return
        app_id = sel[0]

        c = db.conn.cursor()
        c.execute("SELECT name, job FROM applicants WHERE id=?", (app_id,))
        name, job = c.fetchone()
        if not name or not job:
            messagebox.showwarning("Missing", "Name and job title required.")
            return

        fname = f"Offer_{name.replace(' ','_')}_{datetime.date.today()}.pdf"
        pdf = canvas.Canvas(fname, pagesize=LETTER)
        pdf.drawString(80, 750, "Offer of Employment")
        pdf.drawString(80, 710, f"Dear {name},")
        pdf.drawString(80, 670, f"We are pleased to offer you the {job} position.")
        pdf.drawString(80, 630, "We look forward to working with you!")
        pdf.drawString(80, 590, f"Date: {datetime.date.today()}")
        pdf.save()

        messagebox.showinfo("PDF Created", f"Saved as:\n{fname}")

    # ────────────────────────────────────────────────
    #  EMAIL TEMPLATES TAB
    # ────────────────────────────────────────────────
    def build_templates_tab(self):
        f = ttk.Frame(self.tab_templates, padding=15)
        f.pack(fill="both", expand=True)

        left = ttk.Frame(f, width=320)
        left.pack(side="left", fill="y", padx=(0,12))

        right = ttk.Frame(f)
        right.pack(side="right", fill="both", expand=True)

        ttk.Label(left, text="Templates").pack(anchor="w", pady=(0,6))
        self.tpl_list = tk.Listbox(left, width=38, height=22)
        self.tpl_list.pack(fill="both", expand=True)
        self.tpl_list.bind("<<ListboxSelect>>", self.on_template_select)

        bf = ttk.Frame(left)
        bf.pack(fill="x", pady=10)
        ttk.Button(bf, text="➕ New", command=self.new_template).pack(side="left", padx=4)
        ttk.Button(bf, text="🗑 Delete", command=self.delete_template).pack(side="left", padx=4)

        ttk.Label(right, text="Template Name").pack(anchor="w")
        self.tpl_name = ttk.Entry(right)
        self.tpl_name.pack(fill="x", pady=4)

        ttk.Label(right, text="Subject").pack(anchor="w", pady=(12,0))
        self.tpl_subject = ttk.Entry(right)
        self.tpl_subject.pack(fill="x", pady=4)

        ttk.Label(right, text="Body").pack(anchor="w", pady=(12,0))
        self.tpl_body = scrolledtext.ScrolledText(right, height=18)
        self.tpl_body.pack(fill="both", expand=True, pady=4)

        ttk.Button(right, text="💾 Save", command=self.save_template).pack(pady=16)

    def refresh_templates(self):
        self.tpl_list.delete(0, tk.END)
        c = db.conn.cursor()
        for name, in c.execute("SELECT name FROM email_templates ORDER BY name"):
            self.tpl_list.insert(tk.END, name)

    def on_template_select(self, evt):
        if not self.tpl_list.curselection():
            self.tpl_name.delete(0, tk.END)
            self.tpl_subject.delete(0, tk.END)
            self.tpl_body.delete("1.0", tk.END)
            return

        name = self.tpl_list.get(self.tpl_list.curselection())
        c = db.conn.cursor()
        row = c.execute("SELECT name, subject, body FROM email_templates WHERE name=?", (name,)).fetchone()
        if row:
            self.tpl_name.delete(0, tk.END)
            self.tpl_name.insert(0, row[0])
            self.tpl_subject.delete(0, tk.END)
            self.tpl_subject.insert(0, row[1])
            self.tpl_body.delete("1.0", tk.END)
            self.tpl_body.insert("1.0", row[2])

    def new_template(self):
        name = simpledialog.askstring("New Template", "Template name:")
        if not name: return
        name = name.strip()
        try:
            c = db.conn.cursor()
            c.execute("INSERT INTO email_templates (name, subject, body) VALUES (?,?,?)",
                      (name, "Subject line...", "Dear {name},\n\n..."))
            db.conn.commit()
            self.refresh_templates()
            idx = self.tpl_list.get(0, tk.END).index(name)
            self.tpl_list.selection_set(idx)
            self.tpl_list.see(idx)
            self.on_template_select(None)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Name already exists.")

    def delete_template(self):
        if not self.tpl_list.curselection(): return
        name = self.tpl_list.get(self.tpl_list.curselection())
        if not messagebox.askyesno("Delete", f"Delete '{name}'?"): return

        c = db.conn.cursor()
        c.execute("DELETE FROM email_templates WHERE name=?", (name,))
        db.conn.commit()
        self.refresh_templates()
        self.tpl_name.delete(0, tk.END)
        self.tpl_subject.delete(0, tk.END)
        self.tpl_body.delete("1.0", tk.END)

    def save_template(self):
        name = self.tpl_name.get().strip()
        if not name:
            messagebox.showwarning("Required", "Template name is required.")
            return

        c = db.conn.cursor()
        current = ""
        if self.tpl_list.curselection():
            current = self.tpl_list.get(self.tpl_list.curselection())

        if current and current != name:
            if c.execute("SELECT 1 FROM email_templates WHERE name=? AND name!=?", (name, current)).fetchone():
                messagebox.showerror("Error", "Name already in use.")
                return

        body = self.tpl_body.get("1.0", tk.END).rstrip()

        if current:
            c.execute("UPDATE email_templates SET name=?, subject=?, body=? WHERE name=?",
                      (name, self.tpl_subject.get(), body, current))
        else:
            try:
                c.execute("INSERT INTO email_templates (name, subject, body) VALUES (?,?,?)",
                          (name, self.tpl_subject.get(), body))
            except sqlite3.IntegrityError:
                messagebox.showerror("Error", "Name already exists.")
                return

        db.conn.commit()
        self.refresh_templates()
        messagebox.showinfo("Saved", "Template saved.")

    # ────────────────────────────────────────────────
    #  SETTINGS TAB
    # ────────────────────────────────────────────────
    def build_settings_tab(self):
        f = ttk.Frame(self.tab_settings, padding=24)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Settings", font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(0,20))

        # General
        gen = ttk.LabelFrame(f, text="General", padding=16)
        gen.pack(fill="x", pady=12)

        ttk.Label(gen, text="Default applied status:").grid(row=0, column=0, sticky="w", pady=6, padx=8)
        self.default_status = ttk.Combobox(gen, values=STAGES, state="readonly", width=25)
        self.default_status.grid(row=0, column=1, sticky="w", pady=6, padx=8)
        self.default_status.set(db.get_setting("default_status", "Applied"))

        # Integrations
        integ = ttk.LabelFrame(f, text="Job Board Integrations", padding=16)
        integ.pack(fill="both", expand=True, pady=12)

        for board in JOB_BOARDS:
            name = board["name"]
            prefix = board["key_prefix"]
            frame = ttk.Frame(integ)
            frame.pack(fill="x", pady=8)

            ttk.Label(frame, text=f"{name}:").pack(side="left", padx=8)

            ttk.Button(frame, text="Configure", command=lambda b=board: self.configure_integration(b)).pack(side="left", padx=4)
            ttk.Button(frame, text="Test", command=lambda b=board: self.test_connection(b)).pack(side="left", padx=4)

        ttk.Button(f, text="Save General Settings", command=self.save_general_settings).pack(pady=20)

    def configure_integration(self, board):
        prefix = board["key_prefix"]
        current_key = db.get_setting(f"{prefix}_api_key", "")

        key = simpledialog.askstring(
            f"{board['name']} Configuration",
            f"Enter API key for {board['name']} (if required):",
            initialvalue=current_key,
            parent=self.root
        )

        if key is not None:
            db.set_setting(f"{prefix}_api_key", key.strip())
            messagebox.showinfo("Updated", f"{board['name']} settings saved.\nYou can now test the connection.")

    def test_connection(self, board):
        prefix = board["key_prefix"]
        key = db.get_setting(f"{prefix}_api_key")

        if not key and board["needs_api_key"]:
            messagebox.showwarning("Not Configured", f"No API key set for {board['name']}.")
            return

        messagebox.showinfo(
            "Connection Test",
            f"Test for {board['name']}:\n\n"
            f"• API Key: {'present' if key else 'not set'}\n"
            "• Connection: SIMULATED SUCCESS\n\n"
            "(Real API test will be implemented later)"
        )

    def save_general_settings(self):
        db.set_setting("default_status", self.default_status.get())
        messagebox.showinfo("Settings", "General settings saved.")

    # ────────────────────────────────────────────────
    #  REFRESH ALL
    # ────────────────────────────────────────────────
    def refresh_all(self):
        self.refresh_dashboard()
        self.refresh_applicants()
        self.refresh_templates()


# =========================
# START
# =========================
if __name__ == "__main__":
    root = tk.Tk()
    app = HRApp(root)
    root.mainloop()
