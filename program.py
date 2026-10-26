# Código Program.py

import tkinter as tk
import webbrowser
from tkinter import messagebox
import subprocess
import sys
import os

class HubRobosApp:

    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)
    
    def executar_arquivo(self, arquivo):

        if getattr(sys, 'frozen', False):

            pasta_base = os.path.dirname(sys.executable)
            nome_exe = arquivo.replace(".py", ".exe")

            caminho_exe = os.path.join(
                pasta_base,
                nome_exe
            )

            if not os.path.exists(caminho_exe):
                raise FileNotFoundError(
                    f"Executável não encontrado:\n{caminho_exe}"
                )

            return subprocess.Popen(
                [caminho_exe],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )

        else:

            caminho_py = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                arquivo
            )

            if not os.path.exists(caminho_py):
                raise FileNotFoundError(
                    f"Arquivo Python não encontrado:\n{caminho_py}"
                )

            return subprocess.Popen(
                [sys.executable, caminho_py],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Painel Central de Automações")
        self.root.geometry("1280x800")
        self.root.minsize(1100, 700)
        self.root.configure(bg="#f3f6fb")

        self.label_status = None
        self.processos_ativos = {}
        self._montar_interface()
        self._monitorar_processos()

    def _montar_interface(self) -> None:
        frame_principal = tk.Frame(self.root, bg="#f3f6fb")
        frame_principal.pack(fill="both", expand=True, padx=24, pady=24)

        self._criar_topo(frame_principal)
        self.frame_conteudo = tk.Frame(frame_principal, bg="#f3f6fb")
        self.frame_conteudo.pack(fill="both", expand=True)
        self._criar_painel(self.frame_conteudo)

        self._criar_rodape(frame_principal)

    def _criar_topo(self, parent: tk.Frame) -> None:
        topo = tk.Frame(parent, bg="#f3f6fb")
        topo.pack(fill="x", pady=(0, 18))

        tk.Label(
            topo,
            text="Painel Central de Automações",
            font=("Segoe UI", 24, "bold"),
            bg="#f3f6fb",
            fg="#0f172a",
        ).pack(anchor="w")

        tk.Label(
            topo,
            text="Gerenciamento centralizado e completo de aplicações e automações.",
            font=("Segoe UI", 11),
            bg="#f3f6fb",
            fg="#475569",
        ).pack(anchor="w", pady=(6, 0))

        barra_info = tk.Frame(topo, bg="#ffffff", bd=1, relief="solid", padx=14, pady=10)
        barra_info.pack(fill="x", pady=(16, 0))

        frame_nav = tk.Frame(barra_info, bg="#ffffff")
        frame_nav.pack(side="left")

        lbl_hub = tk.Label(
            frame_nav,
            text="Hub principal",
            font=("Segoe UI", 10, "bold"),
            bg="#ffffff",
            fg="#111827",
        )
        lbl_hub.pack(side="left")

        tk.Label(
            frame_nav,
            text=" | ",
            font=("Segoe UI", 10),
            bg="#ffffff",
            fg="#94a3b8",
        ).pack(side="left")

        lbl_base = tk.Label(
            frame_nav,
            text="Base de dados",
            font=("Segoe UI", 10, "underline"),
            bg="#ffffff",
            fg="#2563eb",
            cursor="hand2",
        )
        lbl_base.pack(side="left")

        lbl_base.bind(
            "<Button-1>",
            lambda e: webbrowser.open(
                "https://docs.google.com/spreadsheets/d/1ONfHlk8bM2HuLbdvBWKDVm0FaxRhussgYUtGRQWn5nc/edit?gid=0#gid=0"
            )
        )

        lbl_base.bind(
            "<Enter>",
            lambda e: lbl_base.configure(fg="#1d4ed8")
        )

        lbl_base.bind(
            "<Leave>",
            lambda e: lbl_base.configure(fg="#2563eb")
        )

        tk.Label(
            barra_info,
            text="6 módulos disponíveis",
            font=("Segoe UI", 10),
            bg="#ffffff",
            fg="#64748b",
        ).pack(side="right")

    def _criar_painel(self, parent: tk.Frame) -> None:
        painel = tk.Frame(parent, bg="#f3f6fb")
        painel.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            painel,
            bg="#f3f6fb",
            highlightthickness=0,
            bd=0
        )
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar_y = tk.Scrollbar(painel, orient="vertical", command=canvas.yview)
        scrollbar_y.pack(side="right", fill="y")

        canvas.configure(yscrollcommand=scrollbar_y.set)

        container = tk.Frame(canvas, bg="#f3f6fb")
        janela_canvas = canvas.create_window((0, 0), window=container, anchor="n")

        def atualizar_scroll_region(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def ajustar_largura_frame(event):
            canvas.itemconfigure(janela_canvas, width=event.width)

        def centralizar_grid(event=None):
            largura_canvas = canvas.winfo_width()
            largura_grid = grid.winfo_reqwidth()
            x = max((largura_canvas - largura_grid) // 2, 0)
            canvas.coords(janela_canvas, x, 0)

        container.bind("<Configure>", atualizar_scroll_region)
        canvas.bind("<Configure>", ajustar_largura_frame)
        canvas.bind("<Configure>", centralizar_grid, add="+")

        grid = tk.Frame(container, bg="#f3f6fb")
        grid.pack(pady=40)

        modulos = [
            {
                "titulo": "Robo Despacho de Disponibilidade Financeira",
                "descricao": "Criação de documento sei, que responde a uma solicitação de disponibilidade financeira, captura dados da planilha de BM 2026 para compor informações do documento",
                "arquivo": "robo_despachov3.py",
            },
            {
                "titulo": "Robo Pendências (SEFAZ/SEPLAG)",
                "descricao": "Na planilha de Solicitações SEPLAG - SEFAZ, captura todos os SEIs que não estão concluídos e verifica se tiveram novos documentos",
                "arquivo": "robo_pendencias_seplag_sefaz.py",
            },
            {
                "titulo": "Robo Destaques Orçamentários",
                "descricao": "Na planilha de CONTROLE - DESTAQUES ORÇAMENTÁRIOS, captura todos os SEIs e verifica se tiveram novos documentos",
                "arquivo": "robo_destaques_orcamentarios.py",
            },
            {
                "titulo": "Robo Solicitação de Pagamentos BM 2026",
                "descricao": "Navega entre planilhas de OB/LE/PD em busca de informações sobre o rastreamento do pagamento de BMs.",
                "arquivo": "robo_solicitacao_pagamentos_bm.py",
            },
            {
                "titulo": "Power BI - Atualização GAC",
                "descricao": "Atualiza as bases de dados OB Geral/Empenho Geral e atualiza o power bi pagamentos DAF",
                "arquivo": None,
            },
            {
                "titulo": "Robo Mensagens",
                "descricao": "Captura as informações, do registro com o status LIBERADO e envia mensagens para os responsáveis da aquele setor.",
                "arquivo": None,
            },

        ]

        for indice, modulo in enumerate(modulos):
            linha = indice // 3
            coluna = indice % 3
            card = self._criar_card(
                grid,
                modulo["titulo"],
                modulo["descricao"],
                modulo["arquivo"],
            )
            card.grid(row=linha, column=coluna, padx=14, pady=14)

        def rolar_mousewheel(event):
            if event.delta:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            else:
                if event.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.yview_scroll(1, "units")

        canvas.bind_all("<MouseWheel>", rolar_mousewheel)
        canvas.bind_all("<Button-4>", rolar_mousewheel)
        canvas.bind_all("<Button-5>", rolar_mousewheel)

    def _criar_card(self, parent: tk.Frame, titulo: str, descricao: str, arquivo: str | None) -> tk.Frame:
        card = tk.Frame(
            parent,
            bg="#ffffff",
            bd=1,
            relief="solid",
            width=300,
            height=300,
            cursor="arrow",
            highlightthickness=1,
            highlightbackground="#dbe3f0",
            highlightcolor="#dbe3f0",
        )
        card.pack_propagate(False)

        topo_card = tk.Frame(card, bg="#ffffff")
        topo_card.pack(fill="x", padx=18, pady=(18, 10))

        indicador = tk.Canvas(
            topo_card,
            width=12,
            height=12,
            bg="#ffffff",
            highlightthickness=0,
        )
        indicador.create_oval(2, 2, 10, 10, fill="#2563eb", outline="#2563eb")
        indicador.pack(side="left")

        tk.Label(
            topo_card,
            text="Módulo",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#2563eb",
        ).pack(side="left", padx=(8, 0))

        corpo = tk.Frame(card, bg="#ffffff")
        corpo.pack(fill="both", expand=True, padx=18)

        lbl_titulo = tk.Label(
            corpo,
            text=titulo,
            font=("Segoe UI", 13, "bold"),
            bg="#ffffff",
            fg="#0f172a",
            justify="left",
            wraplength=260,
            anchor="w",
        )
        lbl_titulo.pack(anchor="w")

        lbl_descricao = tk.Label(
            corpo,
            text=descricao,
            font=("Segoe UI", 10),
            bg="#ffffff",
            fg="#64748b",
            justify="left",
            wraplength=260,
            anchor="w",
        )
        lbl_descricao.pack(anchor="w", pady=(10, 0))
        tk.Frame(corpo, bg="#ffffff").pack(expand=True)

        frame_botoes = tk.Frame(card, bg="#ffffff")
        frame_botoes.pack(side="bottom", anchor="w", padx=18, pady=(0, 18))

        robos_continuos = [
            "Robo Despacho de Disponibilidade Financeira"
        ]

        texto_botao = "Executar"

        if titulo in robos_continuos:
            texto_botao = "Ligar"

        botao = tk.Button(
            frame_botoes,
            text=texto_botao,
            font=("Segoe UI", 10, "bold"),
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            cursor="hand2",
        )

        if titulo in robos_continuos:

            botao.config(
                bg="#16a34a",
                activebackground="#15803d",
                command=lambda nome=titulo, arq=arquivo, b=botao:
                self._controlar_robo(nome, arq, b)
            )

        else:

            botao.config(
                command=lambda nome=titulo, arq=arquivo:
                self._abrir_modulo(nome, arq)
            )

        botao.pack(side="left", ipadx=12, ipady=8)

        if titulo in robos_continuos:

            def hover_enter(e, b=botao):

                if b.cget("text") == "Ligar":
                    b.configure(bg="#15803d")
                else:
                    b.configure(bg="#b91c1c")

            def hover_leave(e, b=botao):

                if b.cget("text") == "Ligar":
                    b.configure(bg="#16a34a")
                else:
                    b.configure(bg="#dc2626")

        else:

            def hover_enter(e, b=botao):
                b.configure(bg="#1d4ed8")

            def hover_leave(e, b=botao):
                b.configure(bg="#2563eb")

        botao.bind("<Enter>", hover_enter)
        botao.bind("<Leave>", hover_leave)

        def clicar_card(event=None, nome=titulo, arq=arquivo):
            self._abrir_modulo(nome, arq)

        widgets_clicaveis = [card, topo_card, corpo, lbl_titulo, lbl_descricao, indicador]

        for widget in widgets_clicaveis:
            widget.bind("<Button-1>", clicar_card)
            widget.configure(cursor="hand2")

        return card
    
    def _controlar_robo(self, nome, arquivo, botao):
        pasta_base = os.path.dirname(os.path.abspath(__file__))
        caminho_arquivo = os.path.join(pasta_base, arquivo)
        if nome in self.processos_ativos:
            processo = self.processos_ativos[nome]["processo"]
            try:
                subprocess.call(
                ["taskkill", "/F", "/T", "/PID", str(processo.pid)]
            )
            except:
                pass

            del self.processos_ativos[nome]

            botao.config(
                text="Ligar",
                bg="#16a34a",
                activebackground="#15803d"
            )

            self.label_status.config(
                text=f"Status: {nome} desligado."
            )

            return

        try:
            processo = self.executar_arquivo(arquivo)

            self.processos_ativos[nome] = {
                "processo": processo,
                "botao": botao
            }
            botao.config(
                text="Desligar",
                bg="#dc2626",
                activebackground="#b91c1c"
            )
            self.label_status.config(
                text=f"Status: {nome} ligado."
            )

        except Exception as e:
            messagebox.showerror(
                "Erro",
                f"Erro ao iniciar robô:\n\n{e}"
            )

    def _monitorar_processos(self):

        processos_remover = []

        for nome, dados in self.processos_ativos.items():

            processo = dados["processo"]
            botao = dados["botao"]

            if processo.poll() is not None:

                botao.config(
                    text="Ligar",
                    bg="#16a34a",
                    activebackground="#15803d"
                )

                processos_remover.append(nome)

                self.label_status.config(
                    text=f"Status: {nome} finalizado."
                )

        for nome in processos_remover:
            del self.processos_ativos[nome]

        self.root.after(1000, self._monitorar_processos)

    def _criar_rodape(self, parent: tk.Frame) -> None:
        rodape = tk.Frame(parent, bg="#f3f6fb")
        rodape.pack(fill="x", pady=(18, 0))

        status_box = tk.Frame(rodape, bg="#ffffff", bd=1, relief="solid", padx=14, pady=10)
        status_box.pack(fill="x")

        self.label_status = tk.Label(
            status_box,
            text="Status: painel carregado com sucesso.",
            font=("Segoe UI", 10),
            bg="#ffffff",
            fg="#334155",
            anchor="w",
        )
        self.label_status.pack(fill="x")

    def _hover_card(self, card: tk.Frame, botao: tk.Button, ativo: bool) -> None:
        if ativo:
            card.configure(
                bg="#ffffff",
                highlightbackground="#2563eb",
                highlightcolor="#2563eb",
            )
            botao.configure(bg="#1d4ed8")
        else:
            card.configure(
                bg="#ffffff",
                highlightbackground="#dbe3f0",
                highlightcolor="#dbe3f0",
            )
            botao.configure(bg="#2563eb")

    def _limpar_conteudo(self):
        for widget in self.frame_conteudo.winfo_children():
            widget.destroy()

    def _abrir_modulo(self, nome: str, arquivo: str | None) -> None:
        self.label_status.config(text=f"Status: módulo selecionado -> {nome}")

        if not arquivo:
            messagebox.showwarning("Módulo", f"O módulo '{nome}' ainda não possui arquivo vinculado.")
            return

        if getattr(sys, 'frozen', False):

            pasta_base = os.path.dirname(sys.executable)

            nome_exe = arquivo.replace(".py", ".exe")

            caminho = os.path.join(
                pasta_base,
                nome_exe
            )

        else:

            pasta_base = os.path.dirname(
                os.path.abspath(__file__)
            )

            caminho = os.path.join(
                pasta_base,
                arquivo
            )

        if not os.path.exists(caminho):

            messagebox.showerror(
                "Erro",
                f"Arquivo não encontrado:\n{caminho}"
            )

            return

        precisa_confirmacao = nome.strip().lower().startswith("robo")

        if precisa_confirmacao:
            confirmar = messagebox.askyesno(
                "Confirmar execução",
                f"Deseja executar o módulo '{nome}'?"
            )
            if not confirmar:
                self.label_status.config(text=f"Status: execução cancelada -> {nome}")
                return

        try:
            self.executar_arquivo(arquivo)
            self.label_status.config(text=f"Status: módulo aberto -> {nome}")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir o módulo '{nome}'.\n\nDetalhes: {e}")


def main() -> None:
    root = tk.Tk()
    HubRobosApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
