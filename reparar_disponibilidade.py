"""Diagnóstico e recuperação direcionada de um documento EXISTENTE no SEI.

Coloque ao lado de robo_despacho.py. Este script NUNCA cria documentos.
Inicialmente apenas localiza o documento. A edição deve ser habilitada
manualmente e só depois de conferir o conteúdo existente no SEI.
"""
import re
import traceback

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import robo_despacho as robo

SEI_ALVO = "00609110021696.000419/2026-75"
LINHA_ALVO = 1716
SOLICITACAO_EXISTENTE = "95229231"
DOCUMENTO_EXISTENTE = "95236873"

# Mantenha False na primeira execução: não modifica nem salva documento.
EDITAR_DOCUMENTO_EXISTENTE = False


def abrir_documento_existente(browser):
    """Localiza somente o documento existente; nunca clica em Incluir Documento."""
    browser.switch_to.default_content()
    try:
        WebDriverWait(browser, 15).until(
            EC.presence_of_element_located((By.ID, "ifrArvore"))
        )
        browser.switch_to.frame("ifrArvore")
        links = browser.find_elements(By.TAG_NAME, "a")
        print(f"DIAGNÓSTICO: {len(links)} links na árvore do SEI", flush=True)

        for link in links:
            texto = (link.get_attribute("textContent") or "").strip()
            if (
                "CEHAB - DISPONIBILIDADE FINANCEIRA - GOP" in texto.upper()
                and re.search(rf"(?<!\d){DOCUMENTO_EXISTENTE}(?!\d)", texto)
            ):
                print(f"DOCUMENTO EXISTENTE ENCONTRADO: {texto}", flush=True)
                browser.execute_script("arguments[0].click();", link)
                browser.switch_to.default_content()
                WebDriverWait(browser, 15).until(
                    EC.presence_of_element_located((By.ID, "ifrConteudoVisualizacao"))
                )
                return True
        print(
            "DOCUMENTO NÃO VISÍVEL NA ÁRVORE. Verifique se a pasta II está expandida. "
            "Nenhum documento será criado.",
            flush=True,
        )
        return False
    finally:
        browser.switch_to.default_content()


def main():
    registros = robo.obter_aguardando_sei()
    dados = next(
        (x for x in registros
         if x["linha_planilha"] == LINHA_ALVO
         and str(x["numero_sei"]).strip() == SEI_ALVO),
        None,
    )
    if dados is None:
        print(
            "LINHA NÃO ENCONTRADA ENTRE OS REGISTROS 'AGUARDANDO SEI'. "
            "Confira o status da linha antes de continuar."
        )
        return

    browser = robo.iniciar_robo()
    try:
        if not robo.verificar_recebidos(browser, SEI_ALVO):
            print("PROCESSO NÃO DISPONÍVEL NO CONTROLE DE RECEBIDOS")
            return

        if not abrir_documento_existente(browser):
            return

        if not EDITAR_DOCUMENTO_EXISTENTE:
            print(
                "MODO DIAGNÓSTICO: documento existente localizado. "
                "Nenhuma edição foi executada."
            )
            return

        print("EDITANDO SOMENTE O DOCUMENTO JÁ CRIADO:", DOCUMENTO_EXISTENTE)
        if not robo.abrir_editar_conteudo(browser):
            print("FALHA AO ABRIR O EDITOR DO DOCUMENTO EXISTENTE")
            return

        sucesso = robo.editar_mensagem(
            browser, dados, SOLICITACAO_EXISTENTE, DOCUMENTO_EXISTENTE
        )
        if sucesso:
            print(
                "ROTINA DE EDIÇÃO RETORNOU SUCESSO. "
                "CONFIRA MANUALMENTE O CONTEÚDO E O SALVAMENTO NO SEI "
                "ANTES DE ALTERAR O STATUS DA PLANILHA."
            )
        else:
            print(
                "EDIÇÃO NÃO CONCLUÍDA. NÃO REEXECUTE A CRIAÇÃO; "
                "O DOCUMENTO EXISTENTE CONTINUA SENDO O ALVO."
            )
    except Exception:
        print("ERRO NO MODO RECUPERAÇÃO:")
        traceback.print_exc()
    finally:
        try:
            browser.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
