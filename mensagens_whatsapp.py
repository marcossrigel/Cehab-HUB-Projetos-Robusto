from seleniumbase import SB
import time
import os
import pyperclip
from selenium.webdriver.common.keys import Keys

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

def enviar_mensagem_whatsapp(telefone: str, mensagem: str):

    os.makedirs(CHROME_PROFILE, exist_ok=True)

    with SB(
        uc=False,
        headless=False,
        user_data_dir=CHROME_PROFILE
    ) as sb:

        sb.open(
            f"https://web.whatsapp.com/send?phone=55{telefone}&text="
        )

        sb.wait_for_ready_state_complete()

        wait_for_whatsapp_login(sb, timeout=180)

        caixa = localizar_caixa_mensagem(sb, timeout=30)

        try:
            sb.click(caixa)
        except:
            sb.js_click(caixa)

        time.sleep(1)

        pyperclip.copy(mensagem)

        try:
            el = sb.find_element(caixa)
            el.send_keys(Keys.CONTROL, "v")
        except:
            sb.type(caixa, mensagem)

        time.sleep(1)

        if not clicar_botao_enviar(sb):
            enviar_enter_na_caixa(sb, caixa)

        print(f"✅ Mensagem enviada para {telefone}")

        time.sleep(3)


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


def enviar_mensagem_gop(mensagem: str) -> None:
    os.makedirs(CHROME_PROFILE, exist_ok=True)

    with SB(
        uc=False,
        headless=False,
        user_data_dir=CHROME_PROFILE
    ) as sb:
        sb.open(WHATSAPP_URL)
        sb.wait_for_ready_state_complete()

        wait_for_whatsapp_login(sb, timeout=180)

        abriu = abrir_grupo_pela_lista_lateral(sb, NOME_GRUPO, max_rolagens=30)
        if not abriu:
            raise RuntimeError(f"Não consegui localizar o grupo '{NOME_GRUPO}' na lista lateral.")

        caixa = localizar_caixa_mensagem(sb, timeout=30)

        try:
            sb.click(caixa)
        except Exception:
            sb.js_click(caixa)

        time.sleep(1)

        pyperclip.copy(mensagem)

        colou = False

        try:
            el = sb.find_element(caixa)
            el.send_keys(Keys.CONTROL, "v")
            colou = True
        except Exception:
            pass

        if not colou:
            try:
                sb.type(caixa, mensagem)
                colou = True
            except Exception:
                pass

        if not colou:
            raise RuntimeError("Não consegui preencher a mensagem no WhatsApp.")

        time.sleep(1.5)

        # 🔥 CONTROLE DE ENVIO
        enviado = False

        if clicar_botao_enviar(sb):
            enviado = True
        else:
            time.sleep(1)
            if enviar_enter_na_caixa(sb, caixa):
                enviado = True

        if not enviado:
            raise RuntimeError("Não consegui enviar a mensagem no WhatsApp.")

        # ✅ AGORA SIM VAI FUNCIONAR
        print("⏳ Aguardando 10 segundos antes de fechar...")
        time.sleep(10)



