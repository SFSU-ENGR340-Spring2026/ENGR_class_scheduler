"""
ENGR Class Scheduler - GUI
Main window, Gantt chart, entry point.
Tab classes in tabs.py. DB functions in db.py.
"""

import platform, shutil, subprocess, sys, sqlite3
from collections import defaultdict
from pathlib import Path

import plotly.graph_objects as go
from PySide6.QtCore import Qt
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from tabs import SectionsTab, FacultyTab, TimeSlotsTab
from solver import Scheduler, SHARED_SECTIONS

PALETTE = [
    "#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948",
    "#b07aa1","#ff9da7","#9c755f","#aecfd6","#d37295","#fabfd2",
    "#8cd17d","#86bcb6","#499894","#f1ce63","#79706e","#d4a6c8",
    "#b6992d","#a0cbe8",
]
DAY_ORDER  = ["M","T","W","R","F"]
DAY_LABELS = ["Monday","Tuesday","Wednesday","Thursday","Friday"]
DAY_SPAN   = 2.6; DAY_GAP = 0.3; BAR_PAD = 0.015; MAX_UNDO = 10


def _t2m(t):
    h,m = t.split(":"); return int(h)*60+int(m)

def _open_folder(path):
    s = platform.system()
    cmd = {"Windows":["explorer"],"Darwin":["open"]}.get(s,["xdg-open"])
    subprocess.run(cmd+[str(path)], check=False)

def _merge_shared(rows):
    out=[]
    for row in rows:
        aliases = SHARED_SECTIONS.get(row[0],[])
        if aliases:
            row = [row[0]+"".join(f"/{a.split('-')[1]}" for a in aliases)]+row[1:]
        out.append(row)
    return out

def _day_pos(d): return d*(DAY_SPAN+DAY_GAP)

def _bar_coords(bar):
    bw = DAY_SPAN/bar["total_lanes"]
    x0 = _day_pos(bar["d"])+bar["lane_idx"]*bw+BAR_PAD
    x1 = _day_pos(bar["d"])+(bar["lane_idx"]+1)*bw-BAR_PAD
    return x0, x1

def _assign_lanes(bars):
    if not bars: return bars
    bars.sort(key=lambda b:(b["s"],b["e"]))
    lane_of=[-1]*len(bars)
    for i in range(len(bars)):
        used={lane_of[j] for j in range(i) if bars[j]["s"]<bars[i]["e"] and bars[j]["e"]>bars[i]["s"]}
        lane=0
        while lane in used: lane+=1
        lane_of[i]=lane
    total=max(lane_of)+1
    for i,bar in enumerate(bars): bar["lane_idx"]=lane_of[i]; bar["total_lanes"]=total
    return bars


def build_gantt_html(rows):
    if not rows: return "<html><body><p>No data to show.</p></body></html>"
    all_profs = sorted({r[4] for r in rows if len(r)>=5})
    prof_color = {p:PALETTE[i%len(PALETTE)] for i,p in enumerate(all_profs)}
    bars_by_day = [[],[],[],[],[]]
    for row in rows:
        if len(row)<5: continue
        sec,ctype,days,tstr,prof = row[0],row[1],row[2],row[3],row[4]
        room = row[5] if len(row)>=6 else ""
        try: ss,es=tstr.split("-"); s=_t2m(ss); e=_t2m(es)
        except: continue
        for ch in days:
            if ch in DAY_ORDER:
                bars_by_day[DAY_ORDER.index(ch)].append(
                    dict(section=sec,ctype=ctype,prof=prof,room=room,ss=ss,es=es,s=s,e=e))
    all_bars=[]
    for d in range(5):
        for bar in _assign_lanes(bars_by_day[d]): bar["d"]=d; all_bars.append(bar)
    fig = go.Figure()
    if all_bars:
        x_min=max(0,(min(b["s"] for b in all_bars)//60)*60)
        x_max=min(1440,(max(b["e"] for b in all_bars)//60+1)*60)
    else: x_min,x_max=480,1320
    bg=["#f5f5f5","#ffffff","#f5f5f5","#ffffff","#f5f5f5"]
    shapes=[dict(type="rect",x0=x_min,x1=x_max,y0=_day_pos(d),y1=_day_pos(d)+DAY_SPAN,
                 fillcolor=bg[d],opacity=1.0,line=dict(width=0),layer="below") for d in range(5)]
    shapes+=[dict(type="line",x0=x_min,x1=x_max,y0=_day_pos(d)-DAY_GAP/2,y1=_day_pos(d)-DAY_GAP/2,
                  line=dict(color="#bbbbbb",width=2),layer="below") for d in range(1,5)]
    bars_by_prof = defaultdict(list)
    for bar in all_bars: bars_by_prof[bar["prof"]].append(bar)
    for prof in all_profs:
        px=[]; py=[]; hover=[]; cdata=[]
        for bar in bars_by_prof[prof]:
            y0,y1=_bar_coords(bar); x0,x1=bar["s"],bar["e"]
            px+=[x0,x1,x1,x0,x0,None]; py+=[y0,y0,y1,y1,y0,None]
            tip=(f"<b>{bar['section']}</b><br>Type:{bar['ctype']}<br>"
                 f"Prof:{prof}<br>Room:{bar.get('room') or 'Need Room'}<br>"
                 f"Time:{bar['ss']} – {bar['es']}<br>Day:{DAY_LABELS[bar['d']]}")
            hover+=[tip,tip,tip,tip,tip,None]; cdata+=[bar["section"]]*5+[None]
        fig.add_trace(go.Scatter(x=px,y=py,mode="lines",fill="toself",
            fillcolor=prof_color[prof],line=dict(color="white",width=1.5),
            name=prof,legendgroup=prof,opacity=1.0,
            hovertemplate="%{text}<extra></extra>",text=hover,customdata=cdata))
    annotations=[dict(x=(b["s"]+b["e"])/2,y=sum(_bar_coords(b))/2,
                      text=b["section"].replace("ENGR","").strip(),name=b["prof"],
                      showarrow=False,xanchor="center",yanchor="middle",
                      font=dict(size=9,color="black",family="monospace"),
                      xref="x",yref="y") for b in all_bars]
    x_vals=list(range(x_min,x_max+1,30))
    x_text=[f"{v//60}:00" if v%60==0 else f"{v//60}:30" for v in x_vals]
    fig.update_layout(
        shapes=shapes, annotations=annotations,
        xaxis=dict(tickmode="array",tickvals=x_vals,ticktext=x_text,side="top",
                   range=[x_min,x_max],gridcolor="#e0e0e0",zeroline=False,
                   fixedrange=False,tickangle=-30,tickfont=dict(size=11)),
        yaxis=dict(tickmode="array",tickvals=[_day_pos(d)+DAY_SPAN/2 for d in range(5)],
                   ticktext=DAY_LABELS,autorange="reversed",
                   range=[-0.2,_day_pos(4)+DAY_SPAN+0.2],showgrid=False,
                   zeroline=False,fixedrange=False,tickfont=dict(size=13,color="#222222")),
        dragmode="zoom",plot_bgcolor="white",paper_bgcolor="white",
        margin=dict(l=80,r=20,t=130,b=20),hovermode="closest",
        legend=dict(title="Click to show/hide",orientation="v",x=1.01,y=1,
                    font=dict(size=11),itemclick="toggle",itemdoubleclick="toggleothers"),
        height=750,
        title=dict(text="Weekly Class Schedule<br><span style='font-size:11px;'>"
                   "(click legend to filter · drag to zoom · double-click to reset)</span>",
                   x=0.5,font=dict(size=14)),
    )
    raw = fig.to_html(include_plotlyjs="cdn",full_html=True)
    inject = """
<style>
  #btn-bar{display:flex;gap:8px;padding:8px 12px 0 12px;}
  #btn-bar button{padding:5px 18px;font-size:12px;border:1.5px solid #ccc;
    border-radius:5px;background:#f7f7f7;cursor:pointer;font-family:sans-serif;}
  #btn-bar button:hover{background:#e0e0e0;}
  #btn-bar button.active{background:#4e79a7;color:white;border-color:#4e79a7;}
</style>
<div id="btn-bar">
  <button id="btn-hide">Hide All</button>
  <button id="btn-show">Show All</button>
</div>
<script>
function waitForPlot(cb){
    var n=0,t=setInterval(function(){
        var el=document.querySelector('.plotly-graph-div');
        if(el&&el.data&&el.data.length>0){clearInterval(t);cb(el);}
        if(++n>150)clearInterval(t);},100);}
waitForPlot(function(plot){
    var idx=plot.data.map(function(_,i){return i;});
    var orig=(plot.layout.annotations||[]).map(function(a){return Object.assign({},a);});
    var pmap={};
    orig.forEach(function(a,i){if(a.name){if(!pmap[a.name])pmap[a.name]=[];pmap[a.name].push(i);}});
    var vis={};plot.data.forEach(function(t){vis[t.name]=true;});
    function sync(){
        var upd=orig.map(function(a){return Object.assign({},a,{visible:false});});
        Object.keys(vis).forEach(function(n){
            if(vis[n])(pmap[n]||[]).forEach(function(i){upd[i]=Object.assign({},orig[i],{visible:true});});});
        Plotly.relayout(plot,{annotations:upd});}
    plot.on('plotly_legendclick',function(d){
        var n=d.data[d.curveNumber].name;vis[n]=!vis[n];
        Plotly.restyle(plot,{visible:vis[n]?true:'legendonly'},[d.curveNumber]).then(sync);
        return false;});
    plot.on('plotly_legenddoubleclick',function(d){
        var n=d.data[d.curveNumber].name;
        var anyOther=Object.keys(vis).some(function(k){return k!==n&&vis[k];});
        Object.keys(vis).forEach(function(k){vis[k]=anyOther?(k===n):true;});
        Plotly.restyle(plot,{visible:plot.data.map(function(t){return vis[t.name]?true:'legendonly';})},idx).then(sync);
        return false;});
    document.getElementById('btn-hide').onclick=function(){
        Object.keys(vis).forEach(function(n){vis[n]=false;});
        Plotly.restyle(plot,{visible:'legendonly'},idx).then(sync);
        this.classList.add('active');document.getElementById('btn-show').classList.remove('active');};
    document.getElementById('btn-show').onclick=function(){
        Object.keys(vis).forEach(function(n){vis[n]=true;});
        Plotly.restyle(plot,{visible:true},idx).then(sync);
        this.classList.add('active');document.getElementById('btn-hide').classList.remove('active');};
    plot.on('plotly_click',function(data){
        if(!data||!data.points||!data.points.length)return;
        var sec=data.points[0].customdata;
        if(sec&&sec!==null)document.title='SELECT:'+sec;});});
</script>"""
    return raw.replace("<body>","<body>"+inject,1) if "<body>" in raw else inject+raw


class SchedulerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ENGR Class Scheduler"); self.resize(1400,860)
        self.project_dir = (Path(sys.executable).parent.parent.parent.parent
                            if getattr(sys,"frozen",False) else Path.cwd())
        self.db_path = self.project_dir/"db_classes.db"
        if not self.db_path.exists() and getattr(sys,"frozen",False):
            bundled = Path(sys._MEIPASS)/"db_classes.db"
            if bundled.exists(): shutil.copy(bundled, self.db_path)
        self.all_rows=[]; self._undo_stack=[]; self._section_slot_map={}
        self._build_ui(); self._refresh_paths(); self._ensure_default()

    def _build_ui(self):
        root=QWidget(); self.setCentralWidget(root)
        ml=QVBoxLayout(root); ml.setContentsMargins(8,8,8,8)
        sp=QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(self._left_panel()); sp.addWidget(self._right_panel())
        sp.setStretchFactor(0,3); sp.setStretchFactor(1,5)
        ml.addWidget(sp)

    def _left_panel(self):
        panel=QWidget(); lay=QVBoxLayout(panel); lay.setSpacing(6)
        box=QGroupBox("Project"); form=QFormLayout(box)
        self.dir_edit=QLineEdit(str(self.project_dir)); self.dir_edit.setReadOnly(True)
        browse=QPushButton("Browse…"); browse.clicked.connect(self._pick_dir)
        row=QWidget(); rl=QHBoxLayout(row); rl.setContentsMargins(0,0,0,0)
        rl.addWidget(self.dir_edit); rl.addWidget(browse)
        form.addRow("Folder",row); lay.addWidget(box)
        br=QHBoxLayout()
        run=QPushButton("▶  Run Solver"); run.setFixedHeight(34)
        run.setStyleSheet("font-size:13px;font-weight:bold;background:#4e79a7;color:white;border-radius:5px;")
        run.clicked.connect(self._run_solver)
        save=QPushButton("💾  Save DB"); save.setFixedHeight(34); save.clicked.connect(self._save_db)
        self.restore_btn=QPushButton("↩  Restore"); self.restore_btn.setFixedHeight(34)
        self.restore_btn.setEnabled(False); self.restore_btn.clicked.connect(self._restore_db)
        default=QPushButton("🔄  Default"); default.setFixedHeight(34); default.clicked.connect(self._default_db)
        openfld=QPushButton("📂  Open Folder"); openfld.setFixedHeight(34)
        openfld.clicked.connect(lambda: _open_folder(self.project_dir))
        for w in [run,save,self.restore_btn,default,openfld]: br.addWidget(w)
        lay.addLayout(br)
        self.db_tabs=QTabWidget()
        self._sections_tab=SectionsTab(self.db_path)
        self._faculty_tab=FacultyTab(self.db_path)
        self._slots_tab=TimeSlotsTab(self.db_path)
        self.db_tabs.addTab(self._sections_tab,"Sections")
        self.db_tabs.addTab(self._faculty_tab,"Faculty")
        self.db_tabs.addTab(self._slots_tab,"Time Slots")
        ls=QSplitter(Qt.Orientation.Vertical); ls.addWidget(self.db_tabs)
        self.log_box=QPlainTextEdit(); self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet("font-size:11px;"); ls.addWidget(self.log_box)
        ls.setStretchFactor(0,5); ls.setStretchFactor(1,1); lay.addWidget(ls)
        return panel

    def _right_panel(self):
        panel=QWidget(); lay=QVBoxLayout(panel)
        ar=QHBoxLayout()
        self.summary=QLabel("Run the solver to see the schedule.")
        self.summary.setStyleSheet("font-size:12px;color:#666;"); ar.addWidget(self.summary,stretch=1)
        self.freeze_btn=QPushButton("📌  Freeze"); self.freeze_btn.setFixedHeight(28)
        self.freeze_btn.setEnabled(False); self.freeze_btn.clicked.connect(self._freeze)
        self.unfreeze_btn=QPushButton("🔓  Unfreeze"); self.unfreeze_btn.setFixedHeight(28)
        self.unfreeze_btn.setEnabled(False); self.unfreeze_btn.clicked.connect(self._unfreeze)
        ar.addWidget(self.freeze_btn); ar.addWidget(self.unfreeze_btn); lay.addLayout(ar)
        fr=QHBoxLayout()
        self.f_sec=QLineEdit(); self.f_sec.setPlaceholderText("Filter section…"); self.f_sec.textChanged.connect(self._filter)
        self.f_typ=QLineEdit(); self.f_typ.setPlaceholderText("Filter type…"); self.f_typ.textChanged.connect(self._filter)
        self.f_pro=QLineEdit(); self.f_pro.setPlaceholderText("Filter professor…"); self.f_pro.textChanged.connect(self._filter)
        self.f_day=QLineEdit(); self.f_day.setPlaceholderText("Filter day…"); self.f_day.textChanged.connect(self._filter)
        for w in [self.f_sec,self.f_typ,self.f_pro,self.f_day]: fr.addWidget(w)
        lay.addLayout(fr)
        self.result_tabs=QTabWidget()
        self.table=QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_sel)
        self.result_tabs.addTab(self.table,"Table View")
        self.web=QWebEngineView()
        self.web.titleChanged.connect(self._on_gantt_click)
        self.result_tabs.addTab(self.web,"Gantt Chart")
        self.result_tabs.currentChanged.connect(self._on_tab)
        lay.addWidget(self.result_tabs)
        return panel

    def _refresh_paths(self):
        self.db_path=self.project_dir/"db_classes.db"
        self.dir_edit.setText(str(self.project_dir))
        if self.db_path.exists():
            for t in [self._sections_tab,self._faculty_tab,self._slots_tab]:
                t.db_path=self.db_path; t.load()
        else: self._log("Database not found.")

    def _pick_dir(self):
        f=QFileDialog.getExistingDirectory(self,"Choose project folder",str(self.project_dir))
        if f:
            self.project_dir=Path(f); self._undo_stack.clear()
            self.restore_btn.setEnabled(False); self._refresh_paths(); self._ensure_default()

    def _backup_dir(self):
        d=self.project_dir/".db_backups"; d.mkdir(exist_ok=True); return d

    def _make_backup(self):
        if not self.db_path.exists(): return
        dest=self._backup_dir()/f"db_backup_{len(self._undo_stack)}.db"
        shutil.copy(self.db_path,dest); self._undo_stack.append(dest)
        while len(self._undo_stack)>MAX_UNDO:
            try: self._undo_stack.pop(0).unlink()
            except: pass
        self.restore_btn.setEnabled(True)

    def _ensure_default(self):
        d=self.project_dir/"db_classes_default.db"
        if not d.exists() and self.db_path.exists():
            shutil.copy(self.db_path,d); self._log("💾  Default snapshot saved.")

    def _restore_db(self):
        if not self._undo_stack: self._log("Nothing to restore."); return
        if QMessageBox.question(self,"Restore","Undo last Save DB?")!=QMessageBox.StandardButton.Yes: return
        bk=self._undo_stack.pop(); shutil.copy(bk,self.db_path)
        try: bk.unlink()
        except: pass
        if not self._undo_stack: self.restore_btn.setEnabled(False)
        self._refresh_paths(); self._log("↩  Restored.")

    def _default_db(self):
        d=self.project_dir/"db_classes_default.db"
        if not d.exists(): self._log("⚠️  No default snapshot found."); return
        if QMessageBox.question(self,"Reset","Overwrite DB with default?")!=QMessageBox.StandardButton.Yes: return
        self._make_backup(); shutil.copy(d,self.db_path)
        self._refresh_paths(); self._log("🔄  DB reset to default.")

    def _save_db(self):
        if not self.db_path.exists(): self._log("Database not found."); return
        self._make_backup()
        try:
            self._sections_tab.save(); self._faculty_tab.save(); self._slots_tab.save()
            self._log("💾  Database saved.")
        except Exception as e: self._log(f"Save error: {e}")

    def _on_sel(self):
        has=bool(self.table.selectedItems())
        self.freeze_btn.setEnabled(has); self.unfreeze_btn.setEnabled(has)

    def _on_tab(self, idx): pass

    def _on_gantt_click(self, title):
        if not title.startswith("SELECT:"): return
        sec=title[7:].strip()
        for r in range(self.table.rowCount()):
            item=self.table.item(r,0)
            if item and item.text().split("/")[0].strip()==sec:
                self.table.selectRow(r)
                self.freeze_btn.setEnabled(True); self.unfreeze_btn.setEnabled(True)
                self._log(f"✔  Selected {sec} from Gantt — press Freeze or Unfreeze.")
                return

    def _primary_id(self):
        r=self.table.currentRow()
        if r<0: return None
        item=self.table.item(r,0)
        if not item: return None
        raw=item.text().split("/")[0]
        return raw if raw.startswith("ENGR") else ("ENGR"+raw if "-" in raw else raw)

    def _slot_label(self, slot_id):
        try:
            conn=sqlite3.connect(str(self.db_path)); cur=conn.cursor()
            cur.execute("SELECT day_pattern,start_time,end_time FROM time_slots WHERE slot_id=?",(slot_id,))
            row=cur.fetchone(); conn.close()
            return f"{row[0]} {row[1]}–{row[2]}" if row else str(slot_id)
        except: return str(slot_id)

    def _freeze(self):
        pid=self._primary_id()
        if not pid: return
        slot_id=self._section_slot_map.get(pid)
        if slot_id is None: self._log(f"No slot for {pid} — run solver first."); return
        self._make_backup()
        try:
            conn=sqlite3.connect(str(self.db_path))
            conn.execute("UPDATE db_classes SET frozen_slot_id=? WHERE section_id=?",(slot_id,pid))
            conn.commit(); conn.close()
        except Exception as e: self._log(f"Freeze error: {e}"); return
        self._sections_tab.load()
        self._log(f"📌  {pid} frozen → slot {slot_id} ({self._slot_label(slot_id)})")

    def _unfreeze(self):
        pid=self._primary_id()
        if not pid: return
        self._make_backup()
        try:
            conn=sqlite3.connect(str(self.db_path))
            conn.execute("UPDATE db_classes SET frozen_slot_id=NULL WHERE section_id=?",(pid,))
            conn.commit(); conn.close()
        except Exception as e: self._log(f"Unfreeze error: {e}"); return
        self._sections_tab.load(); self._log(f"🔓  {pid} unfrozen.")

    def _run_solver(self):
        self.log_box.clear()
        if not self.db_path.exists(): self._log("Database not found."); return
        try:
            self._sections_tab.save(); self._faculty_tab.save(); self._slots_tab.save()
        except Exception as e: self._log(f"Save error: {e}"); return
        self._log("Saved edits. Running solver…")
        try: sched=Scheduler(str(self.db_path)); sched.load()
        except Exception as e: self._log(f"Load error: {e}"); return
        if getattr(sched,"skipped_no_faculty",[]):
            from solver import NO_FACULTY_COURSES
            self._log("─"*60); self._log("⚠️  UNSCHEDULED — No qualified faculty:")
            by_course={}
            for sid in sorted(sched.skipped_no_faculty):
                by_course.setdefault(sid.rsplit("-",1)[0],[]).append(sid)
            for cid,sids in sorted(by_course.items()):
                self._log(f"   {cid} — {NO_FACULTY_COURSES.get(cid,cid)}")
                self._log(f"      Sections: {', '.join(sids)}")
            self._log(f"   Total skipped: {len(sched.skipped_no_faculty)} across {len(by_course)} courses")
            self._log("─"*60)
        try: result=sched.solve()
        except Exception as e: self._log(f"Solver error: {e}"); return
        if not result: self._log("Solver finished — no feasible schedule found."); return
        self._section_slot_map={}
        try:
            conn=sqlite3.connect(str(self.db_path)); cur=conn.cursor()
            cur.execute("SELECT slot_id,day_pattern,start_time,end_time FROM time_slots")
            slookup={(r[1],r[2],r[3]):r[0] for r in cur.fetchall()}; conn.close()
            for row in result:
                try:
                    s,e=row[3].split("-"); sid=slookup.get((row[2],s,e))
                    if sid: self._section_slot_map[row[0]]=sid
                except: pass
        except: pass
        db_info={}
        try:
            conn=sqlite3.connect(str(self.db_path)); cur=conn.cursor()
            cur.execute("SELECT section_id,slot_type,capacity,major,lab_room,frozen_slot_id FROM db_classes")
            db_info={r[0]:r[1:] for r in cur.fetchall()}; conn.close()
        except: pass
        rows_full=[]
        for row in result:
            row=list(row); sec=row[0]; typ=row[1]; days=row[2]; time=row[3]; prof=row[4]; room=row[5] if len(row)>=6 else ""
            info=db_info.get(sec,("","","","",""))
            stype=info[0] or ""; cap=str(info[1]) if info[1] else ""
            major=info[2] or ""
            if not room or room=="Need Room": room=info[3] or room
            frozen=str(info[4]) if info[4] else ""
            rows_full.append([sec,typ,stype,days,time,prof,cap,major,room,frozen])
        self.all_rows=_merge_shared(sorted(rows_full,key=lambda r:(r[0],r[4])))
        self._filter()
        n=len(self.all_rows); skipped=len(getattr(sched,"skipped_no_faculty",[]))
        self._log("─"*60); self._log(f"✅  SCHEDULE COMPLETE — {n} sections assigned.")
        if skipped: self._log(f"⚠️  {skipped} section(s) skipped.")
        viol=getattr(sched,"major_overlap_violations",0)
        self._log("✅  All same-major sections at non-overlapping times." if not viol
                  else f"⚠️  {viol} same-major conflict(s).")
        self._log("─"*60)

    def _filter(self):
        if not self.all_rows: return
        fs=self.f_sec.text().strip().lower(); ft=self.f_typ.text().strip().lower()
        fd=self.f_day.text().strip().lower(); fp=self.f_pro.text().strip().lower()
        filtered=[]
        for row in self.all_rows:
            r=(row+[""]*10)[:10]
            if fs and fs not in r[0].lower(): continue
            if ft and ft not in r[1].lower(): continue
            if fd and fd not in r[3].lower(): continue
            if fp and fp not in r[5].lower(): continue
            filtered.append(r)
        hdrs=["Section","Type","Slot Type","Days","Time","Professor","Cap","Major","Room","Frozen Slot"]
        self.table.setSortingEnabled(False); self.table.clear()
        self.table.setColumnCount(len(hdrs)); self.table.setHorizontalHeaderLabels(hdrs)
        self.table.setRowCount(len(filtered))
        for ri,row in enumerate(filtered):
            for ci,val in enumerate(row):
                item=QTableWidgetItem(str(val))
                if ci==6: item.setTextAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(ri,ci,item)
        self.table.setSortingEnabled(True)
        self.summary.setText(f"Showing {len(filtered)} of {len(self.all_rows)} sections"
                             "  — select a row → 📌 Freeze to pin it")
        gantt_rows=[[r[0],r[1],r[3],r[4],r[5],r[8]] for r in filtered]
        self.web.setHtml(build_gantt_html(gantt_rows))

    def _log(self, msg): self.log_box.appendPlainText(msg)


def main():
    app=QApplication(sys.argv)
    w=SchedulerWindow(); w.show()
    sys.exit(app.exec())

if __name__=="__main__":
    main()