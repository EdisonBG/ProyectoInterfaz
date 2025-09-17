import os
import csv
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from .barra_navegacion import BarraNavegacion

SERIES_DEF = {
    "T_horno1": ("Temperatura horno 1", "°C", 3, 1.0),
    "T_horno2": ("Temperatura horno 2", "°C", 4, 1.0),
    "T_omega1": ("Temperatura omega 1", "°C", 1, 1.0),
    "T_omega2": ("Temperatura omega 2", "°C", 2, 1.0),
    "T_cond1":  ("Temperatura condensador 1", "°C", 5, 1.0),
    "T_cond2":  ("Temperatura condensador 2", "°C", 6, 1.0),
    "P_mezcla": ("Presión mezcla", "bar", 7, 0.1),
    "P_H2":     ("Presión H2", "bar", 8, 0.1),
    "P_salida": ("Presión salida", "bar", 9, 0.1),
    "MFC_O2":   ("MFC O2", "mL/min", 10, 0.1),
    "MFC_CO2":  ("MFC CO2", "mL/min", 11, 0.1),
    "MFC_N2":   ("MFC N2", "mL/min", 12, 0.1),
    "MFC_H2":   ("MFC H2", "mL/min", 13, 0.1),
}
SERIES_ORDER = [
    "T_horno1","T_horno2","T_omega1","T_omega2","T_cond1","T_cond2",
    "P_mezcla","P_H2","P_salida","MFC_O2","MFC_CO2","MFC_N2","MFC_H2",
]

class VentanaGraph(tk.Frame):
    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino
        if hasattr(self.controlador, "__setattr__"):
            setattr(self.controlador, "_ventana_graph", self)

        st = ttk.Style(self)
        try: st.theme_use("clam")
        except Exception: pass

        self._BG="#0f172a"; self._SURFACE="#111827"; self._BORDER="#334155"; self._TEXT="#e5e7eb"
        self._PRIMARY="#2563eb"; self._PRIMARY_ACTIVE="#1d4ed8"

        self.configure(bg=self._BG)
        # Fuentes compactas
        self.option_add("*Font", ("TkDefaultFont", 10))
        self.option_add("*TButton.Font", ("TkDefaultFont", 10, "bold"))
        self.option_add("*Entry.Font", ("TkDefaultFont", 10))

        st.configure("Graph.Container.TFrame", background=self._BG)
        st.configure("Graph.Inner.TFrame", background=self._SURFACE)
        st.configure("Graph.TLabel", background=self._SURFACE, foreground=self._TEXT)
        st.configure("Graph.TButton", padding=(8,6), relief="raised", borderwidth=2,
                     background=self._SURFACE, foreground=self._TEXT)
        st.map("Graph.TButton", background=[("active", self._BORDER)])
        st.configure("GraphPrimary.TButton", padding=(8,6), relief="raised", borderwidth=2,
                     background=self._PRIMARY, foreground="white")
        st.map("GraphPrimary.TButton", background=[("active", self._PRIMARY_ACTIVE)])
        st.configure("Graph.TLabelframe", background=self._SURFACE, foreground=self._TEXT, bordercolor=self._BORDER)
        st.configure("Graph.TLabelframe.Label", background=self._SURFACE, foreground=self._TEXT)
        st.configure("Graph.TCheckbutton", background=self._SURFACE, foreground=self._TEXT)

        # Estado
        self._graph_active=False; self._graph_paused=False; self._log_active=False
        self._graph_job=None; self._log_job=None
        self._elapsed_sec=0; self._sample_period=5
        self._max_points=max(1,(2*60*60)//self._sample_period)
        self._last_snapshot=None
        self._buffers={k:[] for k in SERIES_ORDER}; self._times=[]
        self._csv_path=os.path.abspath(os.path.join(os.path.dirname(__file__),"..","registro_proceso.csv"))

        self.fig=None; self.ax=None; self.mpl_canvas=None
        self._lines={}; self._series_vars={}; self._need_legend_refresh=True

        self._build_ui()
        self.bind("<Destroy>", self._on_destroy)

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0,
                                  minsize=getattr(BarraNavegacion,"ANCHO",170))
        self.grid_columnconfigure(1, weight=1)

        barra=BarraNavegacion(self,self.controlador)
        barra.grid(row=0,column=0,sticky="nsw")
        barra.grid_propagate(False)

        wrap=ttk.Frame(self, style="Graph.Container.TFrame")
        wrap.grid(row=0,column=1,sticky="nsew", padx=8, pady=8)
        wrap.grid_rowconfigure(2,weight=1)
        wrap.grid_columnconfigure(0,weight=1)

        controls=ttk.Frame(wrap, style="Graph.Inner.TFrame")
        controls.grid(row=0,column=0,sticky="ew", pady=(0,8))
        for c in range(9): controls.grid_columnconfigure(c,weight=0)
        controls.grid_columnconfigure(8,weight=1)

        self.btn_graph=ttk.Button(controls,text="Iniciar gráfica",
                                  style="GraphPrimary.TButton",command=self._toggle_graph)
        self.btn_graph.grid(row=0,column=0,padx=6,pady=4)
        self.btn_pause=ttk.Button(controls,text="Pausar",
                                  style="Graph.TButton",command=self._toggle_pause,state="disabled")
        self.btn_pause.grid(row=0,column=1,padx=6,pady=4)
        self.btn_log=ttk.Button(controls,text="Iniciar registro (CSV)",
                                style="Graph.TButton",command=self._toggle_log)
        self.btn_log.grid(row=0,column=2,padx=6,pady=4)

        ttk.Label(controls,text="Periodo (s):",style="Graph.TLabel")\
            .grid(row=0,column=3,padx=(16,4),pady=4,sticky="e")
        self.var_period=tk.IntVar(value=self._sample_period)
        spn=ttk.Spinbox(controls,from_=1,to=60,width=4,textvariable=self.var_period,
                        justify="center",command=self._on_period_change)
        spn.grid(row=0,column=4,padx=4,pady=4)
        spn.bind("<Return>",lambda _e:self._on_period_change())
        spn.bind("<FocusOut>",lambda _e:self._on_period_change())

        ttk.Button(controls,text="Seleccionar todo",style="Graph.TButton",
                   command=self._select_all).grid(row=0,column=5,padx=(16,6),pady=4)
        ttk.Button(controls,text="Ninguno",style="Graph.TButton",
                   command=self._select_none).grid(row=0,column=6,padx=6,pady=4)

        self.lbl_status=ttk.Label(controls,text="Gráfica: OFF   |   Registro: OFF",style="Graph.TLabel")
        self.lbl_status.grid(row=0,column=7,padx=8,pady=4,sticky="w")

        selbox=ttk.LabelFrame(wrap,text="Variables a graficar",style="Graph.TLabelframe")
        selbox.grid(row=1,column=0,sticky="ew",pady=(0,8))
        cols=3
        for i,key in enumerate(SERIES_ORDER):
            r,c=divmod(i,cols)
            var=tk.BooleanVar(value=False); self._series_vars[key]=var
            label,unit,*_=SERIES_DEF[key]
            ttk.Checkbutton(selbox,text=f"{label} [{unit}]",variable=var,
                            style="Graph.TCheckbutton",
                            command=self._refresh_legend_next).grid(row=r,column=c,sticky="w",padx=6,pady=2)
        for c in range(cols): selbox.grid_columnconfigure(c,weight=1)

        fig_frame=ttk.Frame(wrap, style="Graph.Inner.TFrame")
        fig_frame.grid(row=2,column=0,sticky="nsew")
        fig_frame.grid_rowconfigure(0,weight=1); fig_frame.grid_columnconfigure(0,weight=1)

        self.fig=Figure(figsize=(9,5), dpi=100)
        self.fig.patch.set_facecolor(self._SURFACE)
        self.ax=self.fig.add_subplot(111)
        self.ax.set_facecolor(self._SURFACE)
        self.ax.tick_params(colors=self._TEXT,labelsize=9)
        for s in self.ax.spines.values(): s.set_color(self._BORDER)
        self.ax.yaxis.label.set_color(self._TEXT); self.ax.xaxis.label.set_color(self._TEXT)
        self.ax.grid(True, linestyle="--", linewidth=0.7, alpha=0.35, color=self._BORDER)
        self.ax.set_xlabel("Tiempo (MM:SS)"); self.ax.set_ylabel("Valor")
        self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

        def _fmt_mmss(x,_pos):
            total=int(max(0,x)); m,s=divmod(total,60); return f"{m:02d}:{s:02d}"
        self.ax.xaxis.set_major_formatter(FuncFormatter(_fmt_mmss))

        for key in SERIES_ORDER:
            ln,=self.ax.plot([],[],label=self._series_label(key))
            self._lines[key]=ln

        self._need_legend_refresh=True; self._refresh_legend()

        self.mpl_canvas=FigureCanvasTkAgg(self.fig, master=fig_frame)
        w=self.mpl_canvas.get_tk_widget()
        w.grid(row=0,column=0,sticky="nsew")
        w.bind("<Map>", lambda _e: self.after(0,self._fit_canvas))
        w.bind("<Configure>", lambda _e: self._fit_canvas())

    def _fit_canvas(self):
        if not self.mpl_canvas or not self.fig: return
        w=self.mpl_canvas.get_tk_widget().winfo_width()
        h=self.mpl_canvas.get_tk_widget().winfo_height()
        if w<=1 or h<=1: return
        self.fig.set_size_inches(w/self.fig.dpi, h/self.fig.dpi, forward=True)
        self.fig.subplots_adjust(left=0,right=1,top=1,bottom=0)
        self.mpl_canvas.draw_idle()

    # --- RX / snapshot ---
    def on_rx_cmd5(self, partes):
        try:
            if not partes or partes[0]!="5": return
            def fidx(i, d=0.0):
                try: return float(partes[i])
                except Exception: return d
            snap={}
            for key in SERIES_ORDER:
                _,_,idx,scale=SERIES_DEF[key]
                val=fidx(idx,0.0)*scale
                if key.startswith("P_") or key.startswith("MFC_"): val=round(val,1)
                snap[key]=val
            self._last_snapshot=snap
        except Exception as ex:
            print("[Graph] Error parseando CMD=5:", ex)

    # --- toggles / ciclos / helpers (igual que antes, con fuentes ya compactas) ---
    def _toggle_graph(self):
        if not self._graph_active:
            if not any(v.get() for v in self._series_vars.values()):
                messagebox.showwarning("Gráfica","Selecciona al menos una variable para graficar."); return
            self._reset_plot_buffers(); self._graph_active=True; self._graph_paused=False
            self.btn_graph.configure(text="Detener gráfica"); self.btn_pause.configure(text="Pausar",state="normal")
            self._graph_tick()
        else:
            self._graph_active=False; self._graph_paused=False
            self.btn_graph.configure(text="Iniciar gráfica"); self.btn_pause.configure(text="Pausar",state="disabled")
            if self._graph_job:
                try: self.after_cancel(self._graph_job)
                except Exception: pass
                self._graph_job=None
            self._reset_plot_buffers()
        self._update_status()

    def _toggle_pause(self):
        if not self._graph_active: return
        self._graph_paused=not self._graph_paused
        self.btn_pause.configure(text=("Reanudar" if self._graph_paused else "Pausar"))
        if not self._graph_paused:
            if self._graph_job:
                try: self.after_cancel(self._graph_job)
                except Exception: pass
            self._graph_job=self.after(self._sample_period*1000,self._graph_tick)
        self._update_status()

    def _toggle_log(self):
        if not self._log_active:
            self._log_active=True; self.btn_log.configure(text="Detener registro (CSV)"); self._log_tick()
        else:
            self._log_active=False; self.btn_log.configure(text="Iniciar registro (CSV)")
            if self._log_job:
                try: self.after_cancel(self._log_job)
                except Exception: pass
                self._log_job=None
        self._update_status()

    def _select_all(self):
        for v in self._series_vars.values(): v.set(True)
        self._refresh_legend_next()

    def _select_none(self):
        for v in self._series_vars.values(): v.set(False)
        self._refresh_legend_next()

    def _update_status(self):
        s="ON" if self._graph_active else "OFF"
        if self._graph_active and self._graph_paused: s+=" (PAUSA)"
        self.lbl_status.configure(text=f"Gráfica: {s}   |   Registro: {'ON' if self._log_active else 'OFF'}   |   Periodo: {self._sample_period}s")

    def _graph_tick(self):
        if not self._graph_active or self._graph_paused: return
        if self._last_snapshot is not None:
            self._elapsed_sec+=self._sample_period
            t=self._elapsed_sec; self._times.append(t)
            if len(self._times)>self._max_points: self._times=self._times[-self._max_points:]
            for key in SERIES_ORDER:
                buf=self._buffers[key]; buf.append(self._last_snapshot.get(key,0.0))
                if len(buf)>self._max_points: self._buffers[key]=buf[-self._max_points:]
            self._redraw_plot()
        self._graph_job=self.after(self._sample_period*1000,self._graph_tick)

    def _log_tick(self):
        if not self._log_active: return
        if self._last_snapshot is not None:
            from datetime import datetime
            ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._append_csv([ts]+[self._last_snapshot.get(k,0.0) for k in SERIES_ORDER])
        self._log_job=self.after(1000,self._log_tick)

    def _series_label(self,key):
        label,unit,*_=SERIES_DEF[key]; return f"{label} [{unit}]"

    def _refresh_legend_next(self):
        self._need_legend_refresh=True; self._refresh_legend()

    def _refresh_legend(self):
        if not self._need_legend_refresh or self.ax is None: return
        handles,labels=[],[]
        for key in SERIES_ORDER:
            if self._series_vars[key].get():
                handles.append(self._lines[key]); labels.append(self._series_label(key))
        leg=self.ax.get_legend()
        if leg: leg.remove()
        if handles:
            leg=self.ax.legend(handles,labels,loc="upper left",fontsize=8,
                               facecolor=self._SURFACE,edgecolor=self._BORDER,labelcolor=self._TEXT)
            for t in leg.get_texts(): t.set_color(self._TEXT)
        self._need_legend_refresh=False
        if self.mpl_canvas: self.mpl_canvas.draw_idle()

    def _redraw_plot(self):
        if self.ax is None or self.mpl_canvas is None: return
        xs=self._times
        for key in SERIES_ORDER:
            ln=self._lines[key]
            ln.set_data(xs,self._buffers[key] if self._series_vars[key].get() else [])
        xmax=max(xs) if xs else 1
        self.ax.set_xlim(left=0,right=xmax if xmax>1 else 1)
        self.ax.relim(); self.ax.autoscale_view(scalex=False,scaley=True)
        self.fig.subplots_adjust(left=0,right=1,top=1,bottom=0)
        self._refresh_legend()
        self.mpl_canvas.draw_idle()

    def _reset_plot_buffers(self):
        self._elapsed_sec=0; self._times=[]
        self._buffers={k:[] for k in SERIES_ORDER}
        for ln in self._lines.values(): ln.set_data([],[])
        self.ax.set_xlim(0,1); self.ax.relim(); self.ax.autoscale_view(scalex=False,scaley=True)
        self.fig.subplots_adjust(left=0,right=1,top=1,bottom=0)
        if self.mpl_canvas: self.mpl_canvas.draw_idle()

    def _on_period_change(self):
        try: val=int(self.var_period.get())
        except Exception: val=self._sample_period
        val=max(1,min(60,val))
        if val!=self._sample_period:
            self._sample_period=val; self.var_period.set(val)
            self._max_points=max(1,(2*60*60)//self._sample_period)
            if self._graph_active and not self._graph_paused:
                if self._graph_job:
                    try: self.after_cancel(self._graph_job)
                    except Exception: pass
                self._graph_job=self.after(self._sample_period*1000,self._graph_tick)
        self._update_status()

    def _append_csv(self,row_values):
        file_exists=os.path.exists(self._csv_path)
        try:
            with open(self._csv_path,"a",newline="",encoding="utf-8") as f:
                w=csv.writer(f,delimiter=",")
                if not file_exists: w.writerow(["timestamp"]+SERIES_ORDER)
                w.writerow(row_values)
        except Exception as ex:
            print("[Graph] Error escribiendo CSV:", ex)

    def _on_destroy(self,_e):
        for job in (self._graph_job,self._log_job):
            if job:
                try: self.after_cancel(job)
                except Exception: pass
        self._graph_job=None; self._log_job=None
