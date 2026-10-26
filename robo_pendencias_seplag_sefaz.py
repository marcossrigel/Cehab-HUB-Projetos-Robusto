import os
import re
import time
import csv
import sys
import pyperclip
import gspread

from dotenv import load_dotenv
from datetime import datetime
from selenium.webdriver.common.keys import Keys
from seleniumbase import SB

from oauth2client.service_account import ServiceAccountCredentials

WHATSAPP_URL = "https://web.whatsapp.com/"
CHROME_PROFILE = r"C:\temp\chrome_profile_whatsapp"
NOME_GRUPO = "GOP - CEHAB"

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, "arquivos_json", "arquivo.env")

load_dotenv(ENV_PATH)

GOOGLE_CREDENTIALS = os.path.join(
    BASE_DIR,
    "arquivos_json",
    "credenciais.json"
)

SEI_CHROME_PROFILE = os.path.join(
    BASE_DIR,
    "chrome_profile_sei"
)

os.makedirs(SEI_CHROME_PROFILE, exist_ok=True)

if not SEI_CHROME_PROFILE:
    raise ValueError("A variável CHROME_PROFILE não foi definida no .env")

SOURCE_SHEET_ID = "1CFI3282Mx7MDw13RK5Vq7cA0BJxKsN3h7pwjBzFVogA"
SOURCE_WORKSHEET = "Acompanhamento 2026"

DB_SHEET_ID = "1ONfHlk8bM2HuLbdvBWKDVm0FaxRhussgYUtGRQWn5nc"
DB_WORKSHEET = "doc_seplag_sefaz"

COL_SEI = "SEI"
COL_STATUS = "STATUS"
COL_DEST = "DESTINATÁRIO"
COL_OBJETO = "OBJETO"

SEI_LOGIN_URL = "https://sei.pe.gov.br/sip/login.php?sigla_orgao_sistema=GOVPE&sigla_sistema=SEI"
XP_USUARIO = '//*[@id="txtUsuario"]'
XP_SENHA = '//*[@id="pwdSenha"]'
CSS_BTN_ACESSAR = '#sbmAcessar'
CSS_SELECT_ORGAO = "#selOrgao"
XP_TXT_PESQUISA_RAPIDA = '//*[@id="txtPesquisaRapida"]'
XP_BTN_LUPA = '//*[@id="spnInfraUnidade"]/img'

ROMAN_RE = re.compile(r"^(?=[IVXLCDM]+$)M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
REGEX_SEI = r"\d{7,}\.\d+\/\d{4}-\d+"
SEI_RE = re.compile(REGEX_SEI)

OUT_DIR = os.path.join(BASE_DIR, "downloaded_files")

def normalize(s: str) -> str:
    return (s or "").strip().upper()


def safe_name(s: str) -> str:
    s = (s or "").strip()
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", s)[:120]


def pick_last_sei_from_cell(cell: str) -> str:
    text = (cell or "").strip()
    if not text:
        return ""
    matches = SEI_RE.findall(text)
    return matches[-1].strip() if matches else text


def fetch_seis_from_sheet_api() -> tuple[list[str], dict[str, str], dict[str, str]]:
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds = ServiceAccountCredentials.from_json_keyfile_name(
        GOOGLE_CREDENTIALS,
        scope
    )
    client = gspread.authorize(creds)

    sh = client.open_by_key(SOURCE_SHEET_ID)
    ws = sh.worksheet(SOURCE_WORKSHEET)
    rows = ws.get_all_records()

    seis = []
    sei_to_dest = {}
    sei_to_objeto = {}

    for r in rows:
        status = normalize(str(r.get(COL_STATUS, "")))
        if "CONCLUÍDO" in status:
            continue

        raw = str(r.get(COL_SEI, "")).strip()
        sei = pick_last_sei_from_cell(raw)
        if not sei:
            continue

        dest = (str(r.get(COL_DEST, "")) or "").strip() or "—"
        objeto = (str(r.get(COL_OBJETO, "")) or "").strip() or "—"

        seis.append(sei)

        if sei not in sei_to_dest:
            sei_to_dest[sei] = dest

        if sei not in sei_to_objeto:
            sei_to_objeto[sei] = objeto

    uniq = list(dict.fromkeys(seis))
    return uniq, sei_to_dest, sei_to_objeto


def abrir_planilha_banco():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds = ServiceAccountCredentials.from_json_keyfile_name(
        GOOGLE_CREDENTIALS,
        scope
    )

    client = gspread.authorize(creds)

    sh = client.open_by_key(DB_SHEET_ID)

    return sh.worksheet(DB_WORKSHEET)

def wait_until_not_visible_text(sb: SB, text: str, timeout: int = 15) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if not sb.is_text_visible(text):
                return
        except Exception:
            return
        time.sleep(0.2)

def confirmar_envio(sb, timeout=15):

    inicio = time.time()

    while time.time() - inicio < timeout:

        if sb.is_element_present('//span[@data-icon="msg-error"]'):
            return False

        if sb.is_element_present('//span[@data-icon="msg-check"]'):
            return True

        if sb.is_element_present('//span[@data-icon="msg-dblcheck"]'):
            return True

        time.sleep(0.5)

    return False

def buscar_ultimo_doc_sheet(ws, sei):

    registros = ws.get("B3:D")

    linha_real = 3

    for row in registros:

        nome = str(row[0]).strip() if len(row) > 0 else ""
        ultimo = str(row[1]).strip() if len(row) > 1 else ""

        if nome == sei:
            return linha_real, ultimo

        linha_real += 1

    return None, ""


def salvar_ultimo_doc_sheet(
    ws,
    linha,
    sei,
    ultimo_documento
):


    data_agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    if linha:

        ws.update(
            f"C{linha}:D{linha}",
            [[ultimo_documento, data_agora]]
        )

    else:

        proxima_linha = len(ws.get("B:B")) + 1

        ws.update(
            f"B{proxima_linha}:D{proxima_linha}",
            [[sei, ultimo_documento, data_agora]]
        )

def wait_for_tree_loaded(sb: SB, timeout: int = 15) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            spans = sb.find_elements("css selector", 'span[id^="span"]')
            icons = sb.find_elements("css selector", 'img[id^="icon"]')
            if spans or icons:
                return
        except Exception:
            pass
        time.sleep(0.2)


def is_roman(s: str) -> bool:
    s = (s or "").strip().upper()
    return bool(s) and bool(ROMAN_RE.match(s))


def sei_quick_search(sb: SB, sei: str) -> None:
    sb.wait_for_element_visible(XP_TXT_PESQUISA_RAPIDA, timeout=30)
    sb.clear(XP_TXT_PESQUISA_RAPIDA)
    sb.type(XP_TXT_PESQUISA_RAPIDA, sei)

    try:
        sb.click(XP_BTN_LUPA)
    except Exception:
        sb.js_click(XP_BTN_LUPA)

    wait_until_not_visible_text(sb, "Aguarde", timeout=15)
    sb.wait_for_ready_state_complete()


def find_tree_frame(sb: SB, timeout: int = 40):
    end = time.time() + timeout
    last_err = None

    while time.time() < end:
        try:
            sb.switch_to_default_content()
            frames = sb.find_elements("css selector", "iframe")
        except Exception as e:
            last_err = e
            time.sleep(0.2)
            continue

        for fr in frames:
            name = (fr.get_attribute("name") or "").strip()
            fid = (fr.get_attribute("id") or "").strip()
            key = name or fid or fr

            try:
                sb.switch_to_default_content()
                sb.switch_to_frame(key)

                spans = sb.find_elements("css selector", 'span[id^="span"]')
                for sp in spans[:80]:
                    txt = (sp.text or "").strip()
                    if txt and (is_roman(txt) or len(txt) > 3):
                        sb.switch_to_default_content()
                        return key
            except Exception as e:
                last_err = e
                continue

        time.sleep(0.2)

    sb.switch_to_default_content()
    raise RuntimeError(f"Não consegui localizar o iframe da árvore. Último erro: {last_err}")


def wait_for_roman_folders(sb: SB, timeout: int = 10) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        spans = sb.find_elements("css selector", 'span[id^="span"]')
        for sp in spans:
            try:
                if not sp.is_displayed():
                    continue
                txt = (sp.text or "").strip()
                if is_roman(txt):
                    return True
            except Exception:
                pass
        time.sleep(0.2)
    return False


def expand_last_roman_folder(sb: SB) -> None:
    spans = sb.find_elements("css selector", 'span[id^="span"]')
    romans = []

    for sp in spans:
        try:
            if not sp.is_displayed():
                continue
            txt = (sp.text or "").strip()
            if is_roman(txt):
                romans.append((txt, sp))
        except Exception:
            continue

    if not romans:
        return

    _, last_sp = romans[-1]
    sb.execute_script("arguments[0].scrollIntoView({block:'center'});", last_sp)

    parent = last_sp.find_element("xpath", "./..")
    imgs = parent.find_elements("css selector", "img")

    for img in imgs:
        try:
            src = (img.get_attribute("src") or "").lower()
            if "plus" in src or "expand" in src:
                img.click()
                wait_for_tree_loaded(sb, timeout=8)
                return
        except Exception:
            pass


def get_visible_files_in_tree(sb: SB) -> list[tuple[str, str]]:
    icons = sb.find_elements("css selector", 'img[id^="icon"]')
    items = []

    for ic in icons:
        try:
            if not ic.is_displayed():
                continue

            icon_id = (ic.get_attribute("id") or "").strip()
            if not icon_id.startswith("icon"):
                continue

            num = icon_id.replace("icon", "").strip()
            if not num.isdigit():
                continue

            span_id = f"span{num}"
            sp = sb.find_element("css selector", f"span#{span_id}")
            if not sp.is_displayed():
                continue

            txt = (sp.text or "").strip()
            if not txt:
                continue

            items.append((num, txt))
        except Exception:
            continue

    if not items:
        raise RuntimeError("Não achei arquivos visíveis na árvore.")

    return items

def wait_for_whatsapp_login(sb: SB, timeout: int = 180) -> None:
    print("⏳ Abrindo WhatsApp Web...")

    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            url = sb.get_current_url()

            if "web.whatsapp.com" in url:
                seletores_logado = [
                    '//div[@id="pane-side"]',
                    '//div[@role="grid"]',
                    '//span[@data-icon="chat"]',
                ]

                for sel in seletores_logado:
                    try:
                        if sb.is_element_visible(sel):
                            print("✅ WhatsApp Web aberto e logado.")
                            return
                    except Exception:
                        pass
        except Exception:
            pass

        time.sleep(1)

    raise RuntimeError(
        "Tempo esgotado aguardando login no WhatsApp Web. "
        "Se for a primeira vez, escaneie o QR Code."
    )


def abrir_grupo_pela_lista_lateral(sb: SB, nome_grupo: str, max_rolagens: int = 25) -> bool:
    print(f"🔎 Procurando grupo na lista lateral: {nome_grupo}")

    sb.wait_for_element_visible('//div[@id="pane-side"]', timeout=30)
    time.sleep(2)

    seletor_grupo = f'//span[@title="{nome_grupo}"]'

    for tentativa in range(max_rolagens):
        print(f"   Tentativa {tentativa + 1}/{max_rolagens}")

        try:
            elementos = sb.find_elements("xpath", seletor_grupo)

            for el in elementos:
                try:
                    if el.is_displayed():
                        print(f"✅ Grupo encontrado: {nome_grupo}")
                        try:
                            el.click()
                        except Exception:
                            sb.execute_script("arguments[0].click();", el)

                        time.sleep(2)
                        print("📂 Grupo aberto com sucesso.")
                        return True
                except Exception:
                    pass
        except Exception:
            pass

        try:
            painel = sb.find_element('//div[@id="pane-side"]')
            sb.execute_script("arguments[0].scrollTop = arguments[0].scrollTop + 700;", painel)
        except Exception:
            try:
                sb.execute_script("""
                    const pane = document.querySelector('#pane-side');
                    if (pane) { pane.scrollTop = pane.scrollTop + 700; }
                """)
            except Exception:
                pass

        time.sleep(1.5)

    return False


def localizar_caixa_mensagem(sb: SB, timeout: int = 30) -> str:
    seletores = [
        '//footer//*[@contenteditable="true"][@data-tab]',
        '//footer//*[@contenteditable="true"]',
        '//div[@contenteditable="true"][@role="textbox"]',
        '//div[@title="Digite uma mensagem"]',
        '//div[@title="Mensagem"]',
    ]

    end_time = time.time() + timeout
    while time.time() < end_time:
        for sel in seletores:
            try:
                if sb.is_element_visible(sel):
                    return sel
            except Exception:
                pass
        time.sleep(0.5)

    raise RuntimeError("Não consegui localizar a caixa de mensagem do WhatsApp.")


def clicar_botao_enviar(sb: SB) -> bool:
    botoes = [
        '//button[@aria-label="Enviar"]',
        '//span[@data-icon="send"]/ancestor::button',
        '//button[.//span[@data-icon="send"]]',
        '//div[@role="button"]//span[@data-icon="send"]/ancestor::div[@role="button"]',
    ]

    for sel in botoes:
        try:
            if sb.is_element_visible(sel, timeout=2):
                try:
                    sb.click(sel)
                except Exception:
                    sb.js_click(sel)
                print("📨 Mensagem enviada clicando no botão.")
                return True
        except Exception:
            pass

    return False


def enviar_enter_na_caixa(sb: SB, caixa: str) -> bool:
    try:
        el = sb.find_element(caixa)
        el.send_keys(Keys.ENTER)
        print("📨 Mensagem enviada com Keys.ENTER.")
        return True
    except Exception:
        pass

    try:
        sb.send_keys(caixa, Keys.ENTER)
        print("📨 Mensagem enviada com sb.send_keys ENTER.")
        return True
    except Exception:
        pass

    try:
        el = sb.find_element(caixa)
        el.send_keys(Keys.RETURN)
        print("📨 Mensagem enviada com Keys.RETURN.")
        return True
    except Exception:
        pass

    return False

def enviar_mensagem(mensagem: str,telefone: str = None,grupo: str = None):

    os.makedirs(CHROME_PROFILE, exist_ok=True)

    with SB(
        uc=False,
        headless=False,
        user_data_dir=CHROME_PROFILE
    ) as sb:

        if telefone:
            sb.open(
                f"https://web.whatsapp.com/send?phone=55{telefone}&text="
            )

        elif grupo:
            sb.open(WHATSAPP_URL)

        else:
            raise RuntimeError(
                "Informe um telefone ou um grupo."
            )

        sb.wait_for_ready_state_complete()

        wait_for_whatsapp_login(sb, timeout=180)

        if telefone:
            localizar_caixa_mensagem(sb, timeout=60)

        if grupo:
            abriu = abrir_grupo_pela_lista_lateral(
                sb,
                grupo,
                max_rolagens=30
            )

            if not abriu:
                raise RuntimeError(
                    f"Não consegui localizar o grupo '{grupo}'."
                )

        caixa = localizar_caixa_mensagem(sb, timeout=30)

        try:
            sb.click(caixa)
        except Exception:
            sb.js_click(caixa)

        time.sleep(1)

        pyperclip.copy(mensagem)

        try:
            el = sb.find_element(caixa)
            el.send_keys(Keys.CONTROL, "v")
        except Exception:
            sb.type(caixa, mensagem)

        time.sleep(1)

        enviado = clicar_botao_enviar(sb)

        if not enviado:
            enviado = enviar_enter_na_caixa(sb, caixa)

        if not enviado:
            raise RuntimeError("Não consegui enviar a mensagem.")

        print("✅ Mensagem enviada.")

        time.sleep(3)

def main():
    try:
        ws_banco = abrir_planilha_banco()

        os.makedirs(OUT_DIR, exist_ok=True)

        seis, sei_to_dest, sei_to_objeto = fetch_seis_from_sheet_api()

        if not seis:
            print("⚠️ Nenhum SEI encontrado (ou todos estão CONCLUÍDO).")
            input()
            return

        print(f"📄 SEIs válidos (não concluídos): {len(seis)}")

        mudancas = {}

        sei_user = os.getenv("SEI_USER")
        sei_pass = os.getenv("SEI_PASS")

        if not sei_user:
            raise ValueError("A variável SEI_USER não foi definida no .env")

        if not sei_pass:
            raise ValueError("A variável SEI_PASS não foi definida no .env")

        with SB(
            uc=False,
            headless=False,
            user_data_dir=SEI_CHROME_PROFILE
        ) as sb:

            sb.open(SEI_LOGIN_URL)
            sb.wait_for_ready_state_complete()

            if not sb.is_element_visible(XP_TXT_PESQUISA_RAPIDA):
                sb.wait_for_element_visible(XP_USUARIO, timeout=30)
                sb.type(XP_USUARIO, sei_user)

                sb.wait_for_element_visible(XP_SENHA, timeout=30)
                sb.type(XP_SENHA, sei_pass)

                sb.wait_for_element_visible(CSS_SELECT_ORGAO, timeout=30)
                sb.select_option_by_text(CSS_SELECT_ORGAO, "CEHAB")

                sb.wait_for_element_visible(CSS_BTN_ACESSAR, timeout=30)
                sb.click(CSS_BTN_ACESSAR)

            try:
                sb.accept_alert(timeout=2)
            except Exception:
                pass

            try:
                sb.switch_to_window(-1)
            except Exception:
                pass

            sb.wait_for_element_visible(XP_TXT_PESQUISA_RAPIDA, timeout=60)

            sei_quick_search(sb, seis[0])
            tree_frame = find_tree_frame(sb, timeout=40)

            for idx, sei in enumerate(seis, start=1):
                print(f"\n[{idx}/{len(seis)}] 🔎 SEI: {sei}")
                print("   👤 Destinatário:", sei_to_dest.get(sei, "—"))
                print("   📌 Objeto      :", sei_to_objeto.get(sei, "—"))

                try:
                    sei_quick_search(sb, sei)

                    sb.switch_to_default_content()
                    sb.switch_to_frame(tree_frame)

                    achou_romano = wait_for_roman_folders(sb, timeout=2)
                    wait_for_tree_loaded(sb, timeout=3)
                    if achou_romano:
                        expand_last_roman_folder(sb)

                    wait_for_tree_loaded(sb, timeout=8)
                    items = get_visible_files_in_tree(sb)
                    textos = [t for _, t in items]

                    linha_sheet, anterior = buscar_ultimo_doc_sheet(ws_banco, sei)

                    ultimo_txt = ""
                    novos = []

                    if items:
                        ultimo_txt = items[-1][1]

                        if not anterior:
                            novos = [items[-1]]
                        elif anterior == ultimo_txt:
                            novos = []
                        elif anterior in textos:
                            idx_prev = textos.index(anterior)
                            novos = items[idx_prev + 1:]
                        else:
                            novos = [items[-1]]

                    novos_txts = [txt for _, txt in novos]
                    qtd_novos = len(novos)
                    mudou = qtd_novos > 0

                    if mudou and novos:
                        mudancas[sei] = {
                            "qtd_novos": qtd_novos,
                            "ultimo": ultimo_txt,
                            "novos": novos_txts,
                        }

                    print("   ✅ Último doc:", ultimo_txt)
                    if anterior:
                        print("   🗂️  Anterior :", anterior)
                    print("   🆕 Novos docs:", qtd_novos)
                    if novos_txts:
                        for t in novos_txts:
                            print("   ->", t)
                    print("   🔁 Mudou?    :", "SIM" if mudou else "NÃO")

                    if ultimo_txt and mudou: 
                        salvar_ultimo_doc_sheet(ws_banco,linha_sheet,sei,ultimo_txt)

                except Exception as e:
                    print("   ❌ Erro neste SEI:", repr(e))
                finally:
                    sb.switch_to_default_content()

        linhas = []
        data_msg = datetime.now().strftime("%d/%m/%Y")

        linhas.append(f"⚠️ Solicitações (Pendências) SEPLAG/SEFAZ --> Acompanhamento 2026 ⚠️ dia {data_msg}")
        linhas.append("📌 SEIs com novos documentos:")
        linhas.append("------------------------------")

        if not mudancas:
            linhas.append("Nenhum SEI mudou ✅")
        else:
            for sei_k, info in mudancas.items():
                dest = sei_to_dest.get(sei_k, "—")
                objeto = sei_to_objeto.get(sei_k, "—")

                linhas.append(f"{sei_k} - {dest}")
                linhas.append(f"Objeto: {objeto}")
                for doc in info.get("novos", []):
                    linhas.append(f"-> {doc}")
                linhas.append("")

        mensagem_final = "\n".join(linhas)

        print("\n==============================")
        print(mensagem_final)
        print("==============================")

        if mudancas: enviar_mensagem(mensagem_final,grupo=NOME_GRUPO)

        print("\n✅ Finalizado com sucesso!")

    except Exception as e:
        print(f"\n❌ Erro geral no robô: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Processo finalizado!")
    print("👉 Você já pode fechar esta janela.")

    input("\nPressione ENTER para fechar...")

if __name__ == "__main__":
    main()
