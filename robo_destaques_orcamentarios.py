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

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, "arquivos_json", "arquivo.env"))

SEI_USER = os.getenv("SEI_USER")
SEI_PASS = os.getenv("SEI_PASS")

SEI_CHROME_PROFILE = os.path.join(
    BASE_DIR,
    "chrome_profile_sei"
)

GOOGLE_CREDENTIALS = os.path.join(
    BASE_DIR,
    "arquivos_json",
    "credenciais.json"
)

SHEET_ID = "18TBjduqkPUF0UxpCJw7Ttz9aVHpPO5taz7uWox7uYyk"
GID = "2091813233"
DB_SHEET_ID = "1ONfHlk8bM2HuLbdvBWKDVm0FaxRhussgYUtGRQWn5nc"
DB_WORKSHEET = "docs_destaques_orcamentarios"
COLUNA_SEI = "SEI"
COLUNA_OBJETO = "OBJETO"

SEI_LOGIN_URL = "https://sei.pe.gov.br/sip/login.php?sigla_orgao_sistema=GOVPE&sigla_sistema=SEI"

XP_USUARIO = '//*[@id="txtUsuario"]'
XP_SENHA = '//*[@id="pwdSenha"]'
CSS_SELECT_ORGAO = '#selOrgao'
CSS_BTN_ACESSAR = "#sbmAcessar"
XP_TXT_PESQUISA_RAPIDA = '//*[@id="txtPesquisaRapida"]'
XP_BTN_LUPA = '//*[@id="spnInfraUnidade"]/img'

ROMAN_RE = re.compile(r"^(?=[IVXLCDM]+$)M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
SEI_RE = re.compile(r"\b\d{10}\.\d{6}/\d{4}-\d{2}\b")

OUT_DIR = os.path.join(BASE_DIR, "downloaded_files")

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
        raise RuntimeError("Não achei arquivos visíveis (img#icon... + span#span...).")

    return items

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
            [[ultimo_documento, data_agora]],
            f"C{linha}:D{linha}"
        )

    else:

        valores_coluna_b = ws.col_values(2)

        proxima_linha = len(valores_coluna_b) + 1

        ws.update(
            values=[[sei, ultimo_documento, data_agora]],
            range_name=f"B{proxima_linha}:D{proxima_linha}"
        )

def save_results_csv(rows: list[dict], csv_path: str) -> None:
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    fieldnames = ["sei", "objeto", "ultimo_doc", "mudou", "qtd_novos"]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

def pick_sei_value(cell: str) -> str:
    text = (cell or "").strip()
    if not text:
        return ""
    matches = SEI_RE.findall(text)
    if matches:
        return matches[-1]
    return text


def fetch_seis_from_sheet_api() -> list[dict]:
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

    sh = client.open_by_key(SHEET_ID)
    ws = sh.get_worksheet_by_id(int(GID))

    rows = ws.get_all_records()

    itens = []
    seen = set()

    for r in rows:
        raw_sei = str(r.get(COLUNA_SEI, "")).strip()
        sei = pick_sei_value(raw_sei)
        objeto = str(r.get(COLUNA_OBJETO, "")).strip()

        if not sei:
            continue

        if sei in seen:
            continue

        itens.append({
            "sei": sei,
            "objeto": objeto,
        })
        seen.add(sei)

    return itens


def is_roman(s: str) -> bool:
    s = (s or "").strip().upper()
    return bool(s) and bool(ROMAN_RE.match(s))


def sei_quick_search(sb: SB, sei: str) -> None:
    sb.wait_for_element_visible(XP_TXT_PESQUISA_RAPIDA, timeout=40)
    sb.click(XP_TXT_PESQUISA_RAPIDA)
    sb.clear(XP_TXT_PESQUISA_RAPIDA)
    sb.type(XP_TXT_PESQUISA_RAPIDA, sei)
    sb.click(XP_BTN_LUPA)
    sb.sleep(2.2)


def find_tree_frame(sb: SB, timeout: int = 60) -> str:
    end = time.time() + timeout
    last_err = None

    while time.time() < end:
        try:
            sb.switch_to_default_content()
            frames = sb.find_elements("css selector", "iframe")
        except Exception as e:
            last_err = e
            time.sleep(0.5)
            continue

        for fr in frames:
            name = (fr.get_attribute("name") or "").strip()
            fid = (fr.get_attribute("id") or "").strip()
            key = name or fid
            if not key:
                continue
            try:
                sb.switch_to_default_content()
                sb.switch_to_frame(key)

                spans = sb.find_elements("css selector", 'span[id^="span"]')
                for sp in spans[:120]:
                    txt = (sp.text or "").strip()
                    if is_roman(txt):
                        sb.switch_to_default_content()
                        return key
            except Exception as e:
                last_err = e
                continue

        time.sleep(0.6)

    sb.switch_to_default_content()
    raise RuntimeError(f"Não consegui localizar o iframe da árvore automaticamente. Último erro: {last_err}")


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
        raise RuntimeError("Não achei nenhuma pasta romana na árvore.")

    _, last_sp = romans[-1]
    sb.execute_script("arguments[0].scrollIntoView({block:'center'});", last_sp)
    sb.sleep(0.15)

    parent = last_sp.find_element("xpath", "./..")
    imgs = parent.find_elements("css selector", "img")
    for img in imgs:
        try:
            src = (img.get_attribute("src") or "").lower()
            if "plus" in src or "expand" in src:
                img.click()
                sb.sleep(0.6)
                return
        except Exception:
            pass

WHATSAPP_URL = "https://web.whatsapp.com/"
CHROME_PROFILE = r"C:\temp\chrome_profile_whatsapp"

os.makedirs(CHROME_PROFILE, exist_ok=True)
NOME_GRUPO = "GOP - CEHAB"


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

def enviar_mensagem(
    mensagem: str,
    telefone: str = None,
    grupo: str = None
):

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

        pasta_hoje = OUT_DIR
        os.makedirs(pasta_hoje, exist_ok=True)

        result_csv_path = os.path.join(OUT_DIR, "sei_last_doc_result.csv")

        itens_planilha = fetch_seis_from_sheet_api()
        if not itens_planilha:
            print("⚠️ Nenhum SEI encontrado na planilha.")
            return

        print(f"📄 SEIs encontrados na planilha: {len(itens_planilha)}")

        results = []
        mudancas = {}

        sei_user = SEI_USER
        sei_pass = SEI_PASS

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
                sb.sleep(0.5)

                sb.wait_for_element_visible(CSS_BTN_ACESSAR, timeout=30)
                sb.click(CSS_BTN_ACESSAR)
                sb.sleep(1.5)

            try:
                sb.accept_alert(timeout=2)
            except Exception:
                pass

            try:
                sb.switch_to_window(-1)
            except Exception:
                pass

            sb.wait_for_element_visible(XP_TXT_PESQUISA_RAPIDA, timeout=60)

            sei_quick_search(sb, itens_planilha[0]["sei"])
            tree_frame = find_tree_frame(sb, timeout=80)

            for idx, item_planilha in enumerate(itens_planilha, start=1):
                sei = item_planilha["sei"]
                objeto = item_planilha["objeto"]

                print(f"\n[{idx}/{len(itens_planilha)}] 🔎 SEI: {sei}")

                try:
                    sei_quick_search(sb, sei)

                    sb.switch_to_default_content()
                    sb.switch_to_frame(tree_frame)

                    expand_last_roman_folder(sb)

                    items = get_visible_files_in_tree(sb)
                    if not items:
                        print("   ⚠️ Nenhum documento encontrado.")
                        continue
                    texts = [t for _, t in items]

                    linha_sheet, anterior = buscar_ultimo_doc_sheet(ws_banco,sei)

                    if anterior and anterior in texts:
                        idx_prev = texts.index(anterior)
                        novos = items[idx_prev + 1:]
                    else:
                        if not items:
                            continue
                        novos = [items[-1]]

                    novos_txts = [txt_item for _, txt_item in novos]
                    ultimo_txt = items[-1][1]
                    qtd_novos = len(novos)
                    mudou = (qtd_novos > 0 and (not anterior or ultimo_txt != anterior))

                    if mudou:
                        mudancas[sei] = {
                            "qtd_novos": qtd_novos,
                            "ultimo": ultimo_txt,
                            "novos": novos_txts,
                            "objeto": objeto,
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
                        salvar_ultimo_doc_sheet(
                            ws_banco,
                            linha_sheet,
                            sei,
                            ultimo_txt
                        )

                        print(f"💾 Sheets atualizado para {sei}: {ultimo_txt}")

                    results.append({
                        "sei": sei,
                        "objeto": objeto,
                        "ultimo_doc": ultimo_txt,
                        "mudou": "SIM" if mudou else "NAO",
                        "qtd_novos": qtd_novos,
                    })

                except Exception as e:
                    print("   ❌ Erro neste SEI:", repr(e))
                    results.append({
                        "sei": sei,
                        "objeto": objeto,
                        "ultimo_doc": "",
                        "mudou": "ERRO",
                        "qtd_novos": 0,
                    })

                finally:
                    sb.switch_to_default_content()

        linhas = []
        data_msg = datetime.now().strftime("%d/%m/%Y")

        linhas.append(f"🚨 CONTROLE - DESTAQUES ORÇAMENTÁRIOS Acompanhamento destaque 2026🚨 dia {data_msg}")
        linhas.append("📌 SEIs com novos documentos:")
        linhas.append("------------------------------")

        if not mudancas:
            linhas.append("Nenhum SEI mudou ✅")
        else:
            for sei_k, info in mudancas.items():
                linhas.append(sei_k)

                objeto_msg = (info.get("objeto") or "").strip()
                if objeto_msg:
                    linhas.append(f"Objeto: {objeto_msg}")

                for doc in info.get("novos", []):
                    linhas.append(f"-> {doc}")

                linhas.append("")

        mensagem_final = "\n".join(linhas)

        print("\n==============================")
        print(mensagem_final)
        print("==============================")

        save_results_csv(results, result_csv_path)

        if mudancas:
            enviar_mensagem(mensagem_final,grupo=NOME_GRUPO)

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
