# ROBÔ DESPACHO — identifica solicitação, copia acesso direto, cria GOP, edita e salva.
# Usa Chrome NUPCO já autenticado na porta 9222. Não assina nem atualiza planilha.
# ATENÇÃO: o processo já teve GOPs de teste; cada execução cria UM GOP real.
import os
import sys
import re
import time
import unicodedata
import traceback
from bs4 import BeautifulSoup
from decimal import Decimal, InvalidOperation
from num2words import num2words
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from datetime import datetime
from collections import defaultdict
from urllib.parse import urlparse, parse_qs
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

ABA = "BMs 2026"
BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
CREDENCIAIS_GOOGLE = os.path.join(BASE_DIR, "arquivos_json", "credenciais_sheets.json")
ENV_PATH = os.path.join(BASE_DIR, "arquivos_json", "arquivo.env")
MODO_VISUAL_DESPACHO = True
PAUSA_ENTRE_ACOES = 1.5

# Somente este processo poderá ser processado no teste.
SEI_ALVO = "0060900175.001099/2026-81"

def conectar_planilha():
    load_dotenv(ENV_PATH)
    planilha_id = os.getenv("PLANILHA_ID")

    if not planilha_id:
        raise ValueError(f"PLANILHA_ID não encontrado em {ENV_PATH}")
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        CREDENCIAIS_GOOGLE, scope
    )
    client = gspread.authorize(creds)
    planilha = client.open_by_key(planilha_id)
    return planilha.worksheet(ABA)



def atualizar_status_apos_gop(dados, numero_gop):
    """
    Atualiza somente a célula STATUS da linha processada.

    Executar exclusivamente depois de confirmar
    o salvamento do GOP e fechar o editor.
    """

    worksheet = conectar_planilha()

    linha = int(dados["linha_planilha"])
    sei_esperado = str(dados["numero_sei"]).strip()

    # Identificar as colunas pelos cabeçalhos.
    cabecalhos = [
        str(valor).strip()
        for valor in worksheet.row_values(1)
    ]

    if cabecalhos.count("STATUS") != 1:
        raise RuntimeError(
            "Coluna STATUS não identificada de forma única."
        )

    if cabecalhos.count("N° do SEI") != 1:
        raise RuntimeError(
            "Coluna N° do SEI não identificada de forma única."
        )

    coluna_status = cabecalhos.index("STATUS") + 1
    coluna_sei = cabecalhos.index("N° do SEI") + 1

    # Confirma que STATUS continua sendo a coluna Z.
    if coluna_status != 26:
        raise RuntimeError(
            "A coluna STATUS mudou de posição. "
            "Atualização interrompida."
        )

    # Relê a linha diretamente do Google Sheets.
    valores = worksheet.row_values(linha)

    def valor_coluna(indice):
        if len(valores) >= indice:
            return str(valores[indice - 1]).strip()
        return ""

    sei_atual = valor_coluna(coluna_sei)
    status_atual = valor_coluna(coluna_status).upper()

    if sei_atual != sei_esperado:
        raise RuntimeError(
            f"Linha {linha} não corresponde ao SEI esperado. "
            "Nenhuma alteração foi realizada."
        )

    # Nunca sobrescrever outro status.
    if status_atual != "AGUARDANDO SEI":
        raise RuntimeError(
            f"Status inesperado na linha {linha}: "
            f"{status_atual!r}. Nenhuma alteração realizada."
        )

    # Altera exclusivamente a célula STATUS.
    celula = f"Z{linha}"

    worksheet.update_acell(
        celula,
        "AGUARDANDO ASSINATURA"
    )

    # Confirma a gravação.
    status_confirmado = (
        worksheet.acell(celula).value or ""
    ).strip().upper()

    if status_confirmado != "AGUARDANDO ASSINATURA":
        raise RuntimeError(
            "O Google Sheets não confirmou "
            "a atualização do status."
        )

    print(
        f"Planilha atualizada: linha {linha} | "
        "AGUARDANDO ASSINATURA"
    )

    print(f"GOP vinculado ao processo: {numero_gop}")

    return True


def obter_aguardando_sei():
    worksheet = conectar_planilha()
    registros = worksheet.get_all_records()
    lista = []

    for idx, linha in enumerate(
        registros,
        start=2
    ):

        status = str(
            linha.get(
                "STATUS",
                ""
            )
        ).strip().upper()

        if status == "AGUARDANDO SEI":
            lista.append({
                "linha_planilha": idx,
                "numero_sei":
                linha.get(
                    "N° do SEI",
                    ""
                ),
                "fonte":
                linha.get(
                    "FONTE",
                    ""
               ),
                "fonte_recurso":
                linha.get(
                    "Fonte de Recursos",
                    ""
                ),
               "ficha_financeira":
                linha.get(
                    "Ficha Financeira",
                    ""
                ),
                "resolucao":
                linha.get(
                    "RESOLUÇÃO",
                    ""
                ),
                "responsavel":
                linha.get(
                    "RESPONSÁVEL",
                    ""
                ),
                "linha_completa":
                worksheet.row_values(idx)
            })
    return lista

def mostrar_criacao(browser, processo, solicitacao):
    if not MODO_VISUAL_DESPACHO:
        return
    browser.switch_to.default_content()
    print(f"[VISUAL] EXIBINDO CHROME: processo {processo}; solicitação {solicitacao}", flush=True)
    browser.maximize_window()
    time.sleep(PAUSA_ENTRE_ACOES)

def passo_visual(descricao, browser=None):
    print(f"[VISUAL] {datetime.now():%H:%M:%S} - {descricao}", flush=True)
    if browser is not None and MODO_VISUAL_DESPACHO:
        time.sleep(PAUSA_ENTRE_ACOES)

def iniciar_robo():
    print("[CHROME] Conectando ao Chrome NUPCO...")
    opcoes = Options()
    opcoes.debugger_address = "127.0.0.1:9222"
    browser = webdriver.Chrome(options=opcoes)
    abas_sei = []

    for handle in browser.window_handles:
        browser.switch_to.window(handle)
        browser.switch_to.default_content()

        url = browser.current_url
        print(f"[CHROME] Aba encontrada: {urlparse(url).path}")

        endereco = urlparse(url)
        parametros = parse_qs(endereco.query)
        acao = parametros.get("acao", [""])[0]

        if (
            endereco.scheme == "https"
            and endereco.hostname == "sei.pe.gov.br"
            and endereco.path == "/sei/controlador.php"
            and acao in (
                "procedimento_controlar",
                "procedimento_trabalhar"
            )
        ):
            abas_sei.append({
                "handle": handle,
                "acao": acao
            })

    if len(abas_sei) != 1:
        raise RuntimeError(
            f"Encontradas {len(abas_sei)} abas válidas do SEI. "
            "Deixe somente uma aba no Controle de Processos "
            "ou no processo desejado."
        )

    selecionada = abas_sei[0]

    browser.switch_to.window(selecionada["handle"])
    browser.switch_to.default_content()

    print("[CHROME] Chrome NUPCO conectado.")
    print("[SEI] Sessão existente selecionada.")
    print("[SEI] Nenhum login automático realizado.")
    print("[SEI] Tela atual:", selecionada["acao"])

    return browser

def verificar_recebidos(browser, numero_sei):

    try:
        tabela = browser.find_element(
            "xpath",
            '//*[@id="tblProcessosRecebidos"]'
        )
        html = tabela.get_attribute(
            "outerHTML"
        )
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(
            html,
            "html.parser"
        )
        links = soup.find_all("a")

        for link in links:
            processo = link.get_text(
                strip=True
            )
            if processo == numero_sei:
                print(f"{numero_sei} ENCONTRADO")
                campo_pesquisa = browser.find_element(
                    "xpath",
                    '//*[@id="txtPesquisaRapida"]'

                )

                campo_pesquisa.clear()
                campo_pesquisa.send_keys(
                    numero_sei
                )
                print(
                    f"{numero_sei} DIGITADO "
                    f"NA PESQUISA"
                )
                lupa = browser.find_element(
                    "xpath",
                    '//*[@id="spnInfraUnidade"]/img'
                )
                lupa.click()
                time.sleep(5)
                return True

        print(f"{numero_sei} NÃO ENCONTRADO")
        print("========================================================================================")

        return False

    except Exception as erro:
        print(
            f"ERRO VERIFICAR RECEBIDOS: "
            f"{erro}"
        )
        return False
    
def normalizar_texto(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(
        caractere for caractere in texto
        if not unicodedata.combining(caractere)
    )
    return re.sub(r"\s+", " ", texto).strip().upper()

def listar_solicitacoes(browser):
    """
    Pesquisa a árvore do SEI e identifica documentos
    de Solicitação de Disponibilidade Financeira.

    Retorna número público, ID interno e texto.
    Não seleciona GOPs nem modifica documentos.
    """
    browser.switch_to.default_content()
    frame = WebDriverWait(browser, 20).until(
        EC.presence_of_element_located((
            By.ID, "ifrArvore"
        ))
    )

    browser.switch_to.frame(frame)
    solicitacoes = []
    try:
        links = browser.find_elements(
            By.CSS_SELECTOR, "a[id^='anchor']"
        )

        for link in links:
            texto = link.text.strip()
            texto_normalizado = normalizar_texto(texto)

            if "SOLICITACAO DE DISPONIBILIDADE FINANCEIRA" not in texto_normalizado:
                continue

            # Ignorar entradas de outro tipo.
            if "CEHAB - DISPONIBILIDADE FINANCEIRA - GOP" in texto_normalizado:
                continue

            # Número público do documento: 8 dígitos.
            numeros = re.findall(
                r"(?<!\d)\d{8}(?!\d)",
                texto
            )

            if len(numeros) != 1:
                print(
                    f"[ÁRVORE] Número ambíguo: {texto}"
                )
                continue

            numero = numeros[0]

            # O ID da âncora representa o ID interno do SEI.
            id_anchor = link.get_attribute("id") or ""

            correspondencia = re.fullmatch(
                r"anchor(\d+)", id_anchor
            )

            if not correspondencia:
                print(
                    f"[ÁRVORE] ID interno não identificado: "
                    f"{texto}"
                )
                continue

            id_interno = correspondencia.group(1)

            solicitacoes.append({
                "numero": numero,
                "texto": texto,
                "id_interno": id_interno
            })

            print(
                f"[ÁRVORE] Solicitação encontrada: {numero}"
            )
            print(f"[ÁRVORE] Nome: {texto}")
            print(f"[ÁRVORE] ID interno: {id_interno}")

    finally:
        browser.switch_to.default_content()

    # Evitar processar duas vezes a mesma âncora.
    identificadores = [
        s["id_interno"] for s in solicitacoes
    ]

    if len(identificadores) != len(set(identificadores)):
        raise RuntimeError(
            "Documentos duplicados na leitura da árvore."
        )

    return solicitacoes

def normalizar_bm(valor):
    texto = normalizar_texto(valor)
    texto = re.sub(r"^BM\s*[-:]?\s*", "", texto)
    texto = re.sub(r"[\s-]+", "", texto)
    resultado = re.fullmatch(r"0*(\d+)([A-Z]{0,2})", texto)
    if not resultado:
        return None
    return f"{int(resultado.group(1))}{resultado.group(2)}"

def extrair_bm_solicitacao(texto):
    texto = normalizar_texto(texto)
    resultado = re.search(
        r"\bBM\s*[-:]?\s*(\d+)\s*-?\s*([A-Z]{0,2})"
        r"\s*\(?\d{8}\)?\s*$",
        texto
    )

    if not resultado:
        return None

    return normalizar_bm(
        resultado.group(1) + resultado.group(2)
    )

def investigar_acesso_direto(browser, solicitacoes):
    """
    Identifica solicitações com endereço de visualização
    utilizável no SEI.
    Não abre documentos nem cria despachos.
    """
    disponiveis = []
    try:
        browser.switch_to.default_content()
        browser.switch_to.frame(
            browser.find_element(By.ID, "ifrArvore")
        )
        links = browser.find_elements(By.TAG_NAME, "a")
        for solicitacao in solicitacoes:
            numero = str(solicitacao["numero"]).strip()
            candidatos = []
            for link in links:
                texto = normalizar_texto(link.text)
                numeros = re.findall(
                    r"(?<!\d)\d{8}(?!\d)",
                    texto
                )
                if (
                    numero in numeros
                    and "CEHAB - SOLICITACAO DE DISPONIBILIDADE FINANCEIRA"
                    in texto
                ):
                    candidatos.append(link)

            if len(candidatos) != 1:
                print(
                    f"DOCUMENTO {numero}: "
                    f"{len(candidatos)} links encontrados. "
                    "Revisão manual."
                )
                return None

            link = candidatos[0]
            href = (link.get_attribute("href") or "").strip()

            if href.lower() == "about:blank" or not href:
                print(
                    f"DOCUMENTO {numero}: "
                    "SEM ENDEREÇO DE VISUALIZAÇÃO"
                )
                continue

            url = urlparse(href)
            parametros = parse_qs(url.query)

            acao = parametros.get("acao", [""])[0]
            id_documento = parametros.get(
                "id_documento", [""]
            )[0]
            id_anchor = link.get_attribute("id") or ""
            endereco_valido = (
                url.scheme == "https"
                and url.hostname == "sei.pe.gov.br"
                and url.path == "/sei/controlador.php"
                and acao == "arvore_visualizar"
                and id_documento.isdigit()
                and id_anchor == f"anchor{id_documento}"
            )

            if endereco_valido:
                print(
                    f"DOCUMENTO {numero}: "
                    "ENDEREÇO DE VISUALIZAÇÃO CONFIRMADO"
                )

                disponiveis.append(solicitacao)

            else:
                print(
                    f"DOCUMENTO {numero}: "
                    "ENDEREÇO NÃO RECONHECIDO. "
                    "Revisão manual."
                )
                return None

        if len(disponiveis) == 1:
            selecionada = disponiveis[0]
            print(
                "SOLICITAÇÃO SELECIONADA:",
                selecionada["numero"]
            )
            return selecionada

        print(
            f"REVISÃO MANUAL: {len(disponiveis)} "
            "solicitações com endereço válido"
        )
        return None

    except Exception as erro:
        print(
            f"ERRO AO INVESTIGAR SOLICITAÇÕES: {erro}"
        )
        return None

    finally:
        browser.switch_to.default_content()


def preparar_lotes(linhas_do_sei, solicitacoes, browser):
    qtd_linhas = len(linhas_do_sei)
    qtd_solicitacoes = len(solicitacoes)
    if not qtd_linhas or not qtd_solicitacoes:
        print("SEM LINHAS OU SOLICITAÇÕES")
        return []



    numero_sei = str(linhas_do_sei[0]["numero_sei"]).strip()



    print(

        f"SEI {numero_sei}: "

        f"{qtd_linhas} linhas / {qtd_solicitacoes} solicitações"

    )



    linhas = sorted(

        linhas_do_sei,

        key=lambda d: d["linha_planilha"]

    )



    # Regra 1: uma ocorrência e uma solicitação

    if qtd_linhas == 1 and qtd_solicitacoes == 1:

        linha = linhas[0]

        solicitacao = solicitacoes[0]



        colunas = linha.get("linha_completa") or []

        bm_planilha = normalizar_bm(

            colunas[13] if len(colunas) > 13 else ""

        )

        bm_sei = extrair_bm_solicitacao(

            solicitacao["texto"]

        )



        if bm_sei and bm_sei != bm_planilha:

            print("BM DIVERGENTE: revisão manual")

            return []



        print(

            f"ASSOCIAÇÃO DIRETA 1:1: "

            f"linha {linha['linha_planilha']} "

            f"-> solicitação {solicitacao['numero']}"

        )



        return [{

            "linhas": [linha],

            "solicitacao": solicitacao

        }]



    # Regra 2: uma solicitação e várias linhas

    if qtd_solicitacoes == 1:

        solicitacao = solicitacoes[0]

        bm_sei = extrair_bm_solicitacao(

            solicitacao["texto"]

        )



        if bm_sei:

            for linha in linhas:

                colunas = linha.get("linha_completa") or []

                bm = normalizar_bm(

                    colunas[13] if len(colunas) > 13 else ""

                )



                if bm != bm_sei:

                    print("BMs DIVERGENTES: revisão manual")

                    return []



        print("DESPACHO CONSOLIDADO")

        return [{

            "linhas": linhas,

            "solicitacao": solicitacao

        }]





    # REGRA: uma ocorrência e várias solicitações

    # Primeiro compara BM; depois investiga acesso direto

    # quando houver mais de uma correspondência.



    if qtd_linhas == 1 and qtd_solicitacoes > 1:



        linha = linhas[0]

        colunas = linha.get("linha_completa") or []



        bm_planilha = normalizar_bm(

            colunas[13] if len(colunas) > 13 else ""

        )



        solicitacoes_com_bm = [

            {

                "solicitacao": s,

                "bm": extrair_bm_solicitacao(s["texto"])

            }

            for s in solicitacoes

        ]



        # Caso A: existem BMs identificáveis no SEI

        com_bm = [

            item for item in solicitacoes_com_bm

            if item["bm"] is not None

        ]



        if com_bm:



            correspondentes = [

                item["solicitacao"]

                for item in com_bm

                if item["bm"] == bm_planilha

            ]



            if len(correspondentes) == 1:

                selecionada = correspondentes[0]



                print(

                    f"BM CONFIRMADO: linha "

                    f"{linha['linha_planilha']} "

                    f"({bm_planilha}) -> "

                    f"solicitação {selecionada['numero']}"

                )



                return [{

                    "linhas": [linha],

                    "solicitacao": selecionada

                }]



            if len(correspondentes) > 1:



                print(

                    f"BM {bm_planilha} REPETIDO EM "

                    f"{len(correspondentes)} SOLICITAÇÕES"

                )



                print(

                    "INVESTIGANDO ACESSO DIRETO "

                    "ENTRE AS SOLICITAÇÕES DO MESMO BM"

                )



                selecionada = investigar_acesso_direto(

                    browser,

                    correspondentes

                )



                if selecionada is None:

                    print(

                        "REVISÃO MANUAL: BM duplicado "

                        "sem acesso único confirmado"

                    )

                    return []



                print(

                    f"BM {bm_planilha} DESEMPATADO: "

                    f"linha {linha['linha_planilha']} "

                    f"-> solicitação {selecionada['numero']}"

                )



                return [{

                    "linhas": [linha],

                    "solicitacao": selecionada

                }]



            print(

                f"REVISÃO MANUAL: BM {bm_planilha} "

                "sem correspondência identificável no SEI"

            )

            return []



        # Caso B: nenhuma solicitação informa o BM

        print(

            "SOLICITAÇÕES SEM BM: "

            "INVESTIGANDO ACESSO DIRETO"

        )



        selecionada = investigar_acesso_direto(

            browser,

            solicitacoes

        )



        if selecionada is None:

            print(

                "REVISÃO MANUAL: não foi possível "

                "identificar solicitação única"

            )

            return []



        print(

            f"ASSOCIAÇÃO POR ACESSO DIRETO: "

            f"linha {linha['linha_planilha']} "

            f"-> solicitação {selecionada['numero']}"

        )



        return [{

            "linhas": [linha],

            "solicitacao": selecionada

        }]



    # Regra 3: várias solicitações

    # Associação obrigatória pelo BM

    por_bm = {}



    for solicitacao in solicitacoes:

        bm = extrair_bm_solicitacao(

            solicitacao["texto"]

        )



        if not bm:

            print(

                "SOLICITAÇÃO SEM BM IDENTIFICÁVEL:",

                solicitacao["texto"]

            )

            return []



        if bm in por_bm:

            print(f"BM DUPLICADO NO SEI: {bm}")

            return []



        por_bm[bm] = solicitacao



    lotes = {}



    for linha in linhas:

        colunas = linha.get("linha_completa") or []



        bm = normalizar_bm(

            colunas[13] if len(colunas) > 13 else ""

        )



        if not bm or bm not in por_bm:

            print(

                f"LINHA {linha['linha_planilha']}: "

                f"BM {bm} sem solicitação correspondente"

            )

            return []



        solicitacao = por_bm[bm]

        numero = solicitacao["numero"]



        if numero not in lotes:

            lotes[numero] = {

                "linhas": [],

                "solicitacao": solicitacao

            }



        lotes[numero]["linhas"].append(linha)



        print(

            f"BM CONFIRMADO: "

            f"linha {linha['linha_planilha']} "

            f"-> BM {bm} "

            f"-> solicitação {numero}"

        )



    return list(lotes.values())


def conferir_responsavel(linhas):

    """Não escolhe arbitrariamente interessado em lote com responsáveis diferentes."""

    responsaveis = {

        normalizar_texto(dados.get("responsavel", ""))

        for dados in linhas

    }

    if len(responsaveis) > 1:

        print("RESPONSÁVEIS DIFERENTES OU INCOMPLETOS NO MESMO DESPACHO: verificar manualmente")

        return False

    return True


def criar_documento(browser, dados, solicitacao):

    try:

        browser.switch_to.default_content()



        numero = str(solicitacao["numero"]).strip()



        if not re.fullmatch(r"\d{8}", numero):

            print("NÚMERO DA SOLICITAÇÃO INVÁLIDO")

            return None



        # Seleciona a solicitação específica pelo número SEI

        browser.switch_to.frame(

            browser.find_element(By.ID, "ifrArvore")

        )



        alvos = [

            link

            for link in browser.find_elements(By.TAG_NAME, "a")

            if (

                "CEHAB - SOLICITAÇÃO DE DISPONIBILIDADE FINANCEIRA"

                in link.text.upper()

                and re.search(

                    rf"(?<!\d){re.escape(numero)}(?!\d)",

                    link.text

                )

            )

        ]



        if len(alvos) != 1:

            print(f"SOLICITAÇÃO {numero} NÃO ENCONTRADA")

            return None



        browser.execute_script(

            "arguments[0].click();",

            alvos[0]

        )



        browser.switch_to.default_content()

        time.sleep(3)



        print(

            f"SOLICITAÇÃO CORRETA SELECIONADA: "

            f"{solicitacao['texto']}"

        )



        # Procura Incluir Documento nos frames principais

        def localizar_botao(_driver):

            browser.switch_to.default_content()



            frames = browser.find_elements(

                By.TAG_NAME, "iframe"

            )



            for frame in frames:

                browser.switch_to.default_content()

                browser.switch_to.frame(frame)



                botoes = browser.find_elements(

                    By.XPATH,

                    '//img[@title="Incluir Documento"]'

                )



                if botoes:

                    return botoes[0]



            browser.switch_to.default_content()

            return False



        botao = WebDriverWait(browser, 20).until(

            localizar_botao

        )





        # O botao foi encontrado dentro de um iframe.

        # Mantemos esse contexto apos o clique.

        browser.execute_script(

            "arguments[0].click();",

            botao

        )



        passo_visual("Botão Incluir Documento acionado", browser)



        def localizar_visualizacao(driver):

            # Primeira tentativa: iframe dentro do contexto atual.

            frames = driver.find_elements(

                By.ID,

                "ifrVisualizacao"

            )



            if frames:

                return frames[0]



            # Segunda tentativa: contexto principal.

            driver.switch_to.default_content()



            frames = driver.find_elements(

                By.ID,

                "ifrVisualizacao"

            )



            if frames:

                return frames[0]



            return False



        iframe_visualizacao = WebDriverWait(

            browser, 20

        ).until(localizar_visualizacao)



        browser.switch_to.frame(

            iframe_visualizacao

        )



        passo_visual("Tela de inclusão de documento localizada", browser)





        documento_gop = browser.find_element(
            By.XPATH,
            '//*[@id="tblSeries"]/tbody/tr[2]/td/a[2]'
        )
        # Impede escolher um modelo diferente se a ordem da lista mudar.
        texto_modelo = (documento_gop.text or "").strip().upper()
        if not texto_modelo:
            texto_modelo = documento_gop.find_element(
                By.XPATH, "ancestor::tr"
            ).text.strip().upper()
        if "CEHAB - DISPONIBILIDADE FINANCEIRA - GOP" not in texto_modelo:
            raise RuntimeError(f"Modelo de documento inesperado: {texto_modelo!r}")



        browser.execute_script(



            "arguments[0].click();",



            documento_gop



        )



        time.sleep(5)



        campo_destinatario = browser.find_element(



            "id",



            "txtDestinatario"



        )



        campo_destinatario.send_keys(



            "GAC"



        )



        time.sleep(1)



        campo_destinatario.send_keys(



            Keys.ESCAPE



        )



        responsavel = str(



            dados.get("responsavel", "")



        ).strip()



        while True:



            interessados = browser.find_elements(



                By.XPATH,



                '//*[@id="selInteressados"]/option'



            )



            if not interessados:



                break



            interessado_existente = interessados[0]



            print(



                f"REMOVENDO INTERESSADO PRÉ-DEFINIDO: "



                f"{interessado_existente.text}"



            )



            browser.execute_script(



                "arguments[0].selected = true;",



                interessado_existente



            )



            botao_remover = browser.find_element(



                By.XPATH,



                '//*[@id="imgRemoverInteressados"]'



            )



            browser.execute_script(



                "arguments[0].click();",



                botao_remover



            )



            time.sleep(1)



        print(



            "INTERESSADOS PRÉ-DEFINIDOS REMOVIDOS"



        )



        if responsavel:



            campo_interessado = browser.find_element(



                By.XPATH,



                '//*[@id="txtInteressado"]'



            )



            campo_interessado.clear()



            campo_interessado.send_keys(



                responsavel



            )



            print(



                f"BUSCANDO RESPONSÁVEL: {responsavel}"



            )



            time.sleep(2)



            campo_interessado.send_keys(



                Keys.ARROW_DOWN



            )



            time.sleep(1)



            campo_interessado.send_keys(



                Keys.ENTER



            )



            time.sleep(2)



            print(



                f"RESPONSÁVEL SELECIONADO: {responsavel}"



            )



        else:



            print(



                "RESPONSÁVEL VAZIO - "



                "INTERESSADOS PERMANECERÁ VAZIO"



            )



        radio_publico = browser.find_element(



            "id",



            "optPublico"



        )



        browser.execute_script(



            "arguments[0].click();",



            radio_publico



        )



        time.sleep(1)



        botao_salvar = browser.find_element(



            "id",



            "btnSalvar"



        )



        browser.execute_script(



            "arguments[0].click();",



            botao_salvar



        )



        time.sleep(5)



        browser.switch_to.default_content()



        return numero



    except Exception as erro:



        print(



            f"ERRO: {erro}"



        )



        return None


def listar_ids_gop(browser):



    browser.switch_to.default_content()



    browser.switch_to.frame(



        browser.find_element(By.ID, "ifrArvore")



    )



    ids = set()



    for link in browser.find_elements(By.TAG_NAME, "a"):



        texto = link.text.strip()



        if "CEHAB - DISPONIBILIDADE FINANCEIRA - GOP" in texto.upper():



            numero = re.search(r"(\d{8})\)?\s*$", texto)



            if numero:



                ids.add(numero.group(1))



    browser.switch_to.default_content()



    return ids


def janela_principal_sei(browser):
    """Seleciona a janela do processo, nunca uma janela editor_montar."""
    for handle in browser.window_handles:
        browser.switch_to.window(handle)
        browser.switch_to.default_content()
        if "acao=procedimento_trabalhar" in browser.current_url:
            return handle
    raise RuntimeError("Janela principal do processo SEI não encontrada")


def fechar_editor_automatico(browser, janela_principal, limite=20):
    """Fecha o editor inicial e captura o ID INTERNO exato do GOP recém-criado."""
    passo_visual("Verificando editor aberto após inclusão do documento", browser)
    fim = time.time() + limite
    dados = None
    while time.time() < fim:
        for handle in list(browser.window_handles):
            if handle == janela_principal:
                continue
            browser.switch_to.window(handle)
            browser.switch_to.default_content()
            url = browser.current_url
            if "acao=editor_montar" not in url:
                continue
            parametros = parse_qs(urlparse(url).query)
            id_interno = parametros.get("id_documento", [""])[0]
            if not id_interno.isdigit():
                raise RuntimeError("Editor inicial sem ID interno válido; não selecionar GOP às cegas")
            titulo = browser.title
            numero_publico = re.search(r"(?<!\d)(\d{8})(?!\d)", titulo)
            dados = {"id_interno": id_interno, "numero_sei": numero_publico.group(1) if numero_publico else None}
            print(f"[GOP] Editor inicial: ID interno={id_interno}, número SEI={dados['numero_sei'] or 'não disponível'}")
            print("[JANELA] Fechando editor automático inicial", flush=True)
            browser.close()
            break
        if dados:
            break
        time.sleep(0.4)
    browser.switch_to.window(janela_principal)
    browser.switch_to.default_content()
    if not dados:
        raise RuntimeError("Editor inicial não apareceu: não é seguro tentar editar outro GOP")
    print("[JANELA] Processo SEI em primeiro plano; editor inicial fechado=True", flush=True)
    return dados


def selecionar_gop_recem_criado(browser, id_interno, numero_publico=None, limite=20):
    """Seleciona na árvore o documento recém-criado pelo ID interno, não o último GOP."""
    fim = time.time() + limite
    while time.time() < fim:
        browser.switch_to.default_content()
        frame = WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.ID, "ifrArvore")))
        browser.switch_to.frame(frame)
        links = browser.find_elements(By.CSS_SELECTOR, f"a#anchor{id_interno}")
        # Reserva: confirma tanto ID interno no href quanto o nome do GOP.
        if not links:
            links = [a for a in browser.find_elements(By.TAG_NAME, "a")
                     if f"id_documento={id_interno}" in (a.get_attribute("href") or "")
                     and "CEHAB - DISPONIBILIDADE FINANCEIRA - GOP" in a.text.upper()]
        if len(links) == 1:
            texto = links[0].text.strip()
            if "CEHAB - DISPONIBILIDADE FINANCEIRA - GOP" not in texto.upper():
                raise RuntimeError(f"ID interno {id_interno} corresponde a documento inesperado: {texto!r}")
            if numero_publico and numero_publico not in texto:
                raise RuntimeError(f"Número do GOP diverge: título={numero_publico}, árvore={texto!r}")
            print(f"[ÁRVORE] Selecionando GOP recém-criado: {texto}", flush=True)
            browser.execute_script("arguments[0].click();", links[0])
            browser.switch_to.default_content()
            time.sleep(3)
            return True
        if len(links) > 1:
            raise RuntimeError(f"ID interno {id_interno} repetido na árvore; intervenção manual")
        browser.switch_to.default_content()
        time.sleep(0.6)
    raise RuntimeError(f"GOP interno {id_interno} não apareceu na árvore; não será aberto outro documento")



def clicar_editar_conteudo(browser, id_interno_gop, limite=40):
    principal = janela_principal_sei(browser)
    esperado = str(id_interno_gop)

    browser.switch_to.window(principal)
    browser.switch_to.default_content()

    handles_antes = set(browser.window_handles)

    xpath = (
        "//*[@title or @alt or @aria-label]"
    )

    def procurar(caminho=(), nivel=0):
        elementos = browser.find_elements(By.XPATH, xpath)

        for elemento in elementos:
            descricao = normalizar_texto(
                " ".join([
                    elemento.get_attribute("title") or "",
                    elemento.get_attribute("alt") or "",
                    elemento.get_attribute("aria-label") or ""
                ])
            )

            if (
                "EDITAR CONTEUDO" in descricao
                and elemento.is_displayed()
                and elemento.is_enabled()
            ):
                return caminho

        if nivel >= 5:
            return None

        frames = browser.find_elements(By.TAG_NAME, "iframe")

        for indice, frame in enumerate(frames):
            browser.switch_to.frame(frame)

            try:
                resultado = procurar(
                    caminho + (indice,),
                    nivel + 1
                )

                if resultado is not None:
                    return resultado
            finally:
                browser.switch_to.parent_frame()

        return None

    def localizar_caminho(driver):
        driver.switch_to.default_content()
        return procurar()

    # O caminho vazio () representa o documento principal.
    caminho = None
    fim_busca = time.monotonic() + 20

    while time.monotonic() < fim_busca:
        caminho = localizar_caminho(browser)
        if caminho is not None:
            break
        time.sleep(0.5)

    if caminho is None:
        raise RuntimeError(
            "Botão Editar Conteúdo não localizado."
        )

    browser.switch_to.default_content()

    for indice in caminho:
        frames = browser.find_elements(By.TAG_NAME, "iframe")
        browser.switch_to.frame(frames[indice])

    botoes = []

    for elemento in browser.find_elements(By.XPATH, xpath):
        descricao = normalizar_texto(
            " ".join([
                elemento.get_attribute("title") or "",
                elemento.get_attribute("alt") or "",
                elemento.get_attribute("aria-label") or ""
            ])
        )

        if (
            "EDITAR CONTEUDO" in descricao
            and elemento.is_displayed()
            and elemento.is_enabled()
        ):
            botoes.append(elemento)

    if len(botoes) != 1:
        raise RuntimeError(
            f"Encontrados {len(botoes)} botões Editar Conteúdo."
        )

    print("Clicando em Editar Conteúdo...")
    botoes[0].click()

    browser.switch_to.default_content()

    inicio = time.monotonic()

    while time.monotonic() - inicio < limite:
        for handle in browser.window_handles:
            if handle == principal:
                continue

            browser.switch_to.window(handle)
            browser.switch_to.default_content()

            parametros = parse_qs(
                urlparse(browser.current_url).query
            )

            if parametros.get("acao", [""])[0] != "editor_montar":
                continue

            id_aberto = parametros.get(
                "id_documento", [""]
            )[0]

            if id_aberto != esperado:
                raise RuntimeError(
                    f"Editor de outro GOP: {id_aberto}"
                )

            WebDriverWait(browser, 20).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    '[id^="txaEditor_"][contenteditable="true"]'
                ))
            )

            if MODO_VISUAL_DESPACHO:
                browser.maximize_window()

            print("Editor de conteúdo aberto.")
            return True

        time.sleep(0.5)

    browser.switch_to.window(principal)

    raise RuntimeError(
        "O clique foi realizado, mas a janela "
        "do editor não foi identificada."
    )



def testar_edicao_marcador(browser, gop):
    """
    Testa somente a substituição de XX (),
    sem salvar o documento.
    """

    browser.switch_to.default_content()

    marcador = WebDriverWait(browser, 20).until(
        EC.presence_of_element_located((
            By.XPATH,
            '//*[starts-with(@id, "txaEditor_")]'
            '//p[contains(., "Em atendimento ao despacho")]'
            '//strong[1]'
        ))
    )

    original = marcador.text.strip()

    if original != "XX (),":
        raise RuntimeError(
            f"Marcador inesperado: {original!r}"
        )

    numero = SOLICITACAO_ALVO

    resultado = browser.execute_script("""
        const elemento = arguments[0];
        const novoTexto = arguments[1];

        const selecao = window.getSelection();
        const intervalo = document.createRange();

        intervalo.selectNodeContents(elemento);
        selecao.removeAllRanges();
        selecao.addRange(intervalo);

        const editor = elemento.closest('[contenteditable="true"]');

        if (!editor) {
            return {
                executado: false,
                erro: "Elemento não está dentro de uma área editável"
            };
        }

        editor.focus();

        const executado = document.execCommand(
            'insertText',
            false,
            novoTexto
        );

        return {
            executado: executado,
            texto: elemento.innerText,
            html: elemento.outerHTML
        };
    """, marcador, f"{numero},")

    print("[TESTE] Resultado:", resultado)

    # Confirmar novamente após perder o foco.
    browser.find_element(By.TAG_NAME, "body").click()
    time.sleep(2)

    atual = browser.find_element(
        By.XPATH,
        '//*[starts-with(@id, "txaEditor_")]'
        '//p[contains(., "Em atendimento ao despacho")]'
        '//strong[1]'
    ).text.strip()

    print(f"[TESTE] Texto após perder o foco: {atual!r}")

    if atual != f"{numero},":
        raise RuntimeError(
            "O editor não manteve a alteração."
        )

    print("[TESTE] Primeiro marcador alterado com sucesso.")
    print("[PARADA] Documento ainda não foi salvo.")


def preencher_ckeditor(browser, dados, solicitacao, gop):
    """
    Preenche o GOP já aberto no CKEditor.
    Não cria documento, não salva e não atualiza planilha.
    """

    print("[ETAPA 5] Iniciando preenchimento do CKEditor...")

    # 1. Preparar os dados da planilha.
    colunas = dados["linha_completa"]

    if len(colunas) < 15:
        raise ValueError("Linha da planilha sem BM ou valor.")

    numero_bm = str(colunas[13]).strip()
    valor_original = str(colunas[14]).strip()

    if not numero_bm or not valor_original:
        raise ValueError("BM ou valor não preenchido na planilha.")

    valor_limpo = valor_original.replace("R$", "").replace(" ", "")
    valor_limpo = valor_limpo.replace(".", "").replace(",", ".")

    try:
        valor_decimal = Decimal(valor_limpo).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError(f"Valor financeiro inválido: {valor_original}")

    if valor_decimal <= 0:
        raise ValueError("O valor financeiro deve ser positivo.")

    valor_formatado = (
        f"{valor_decimal:,.2f}"
        .replace(",", "#")
        .replace(".", ",")
        .replace("#", ".")
    )

    valor_extenso = num2words(
        valor_decimal,
        lang="pt_BR",
        to="currency"
    )

    fonte_original = str(dados.get("fonte", "")).strip()
    fonte = re.sub(r"\D", "", fonte_original).zfill(10)
    ficha = str(dados.get("ficha_financeira", "")).strip()

    if not fonte_original or not ficha:
        raise ValueError("Fonte ou ficha financeira não informada.")

    fonte_completa = f"{fonte} ({ficha})"
    numero_solicitacao = str(solicitacao)
    numero_gop = str(gop["numero_sei"])
    numero_processo = str(dados["numero_sei"]).strip()

    print(f"[PLANILHA] Solicitação: {numero_solicitacao}")
    print(f"[PLANILHA] BM: {numero_bm}")
    print(f"[PLANILHA] Valor: R$ {valor_formatado}")
    print(f"[PLANILHA] Fonte: {fonte_completa}")
    print(f"[GOP] Número: {numero_gop}")

    
    # 2. Localizar o editor de forma segura.
    browser.switch_to.default_content()

    def localizar_editor(driver):
        return driver.execute_script("""
            const area = document.querySelector(
                '[id^="txaEditor_"][contenteditable="true"], ' +
                '[contenteditable="true"].cke_editable, ' +
                '[contenteditable="true"][role="textbox"]'
            );

            if (!area) return null;

            let nome = null;

            if (window.CKEDITOR &&
                window.CKEDITOR.instances) {

                for (const [chave, instancia] of
                     Object.entries(window.CKEDITOR.instances)) {

                    if (instancia &&
                        instancia.status === 'ready') {
                        nome = chave;
                        break;
                    }
                }
            }

            return {
                id: area.id,
                nome: nome,
                html: area.innerHTML
            };
        """)

    editor_info = WebDriverWait(browser, 25).until(
        localizar_editor
    )

    id_area = editor_info["id"]
    nome_editor = editor_info["nome"]
    html_original = editor_info["html"]

    if not id_area:
        raise RuntimeError(
            "Área editável sem ID; interrompendo por segurança."
        )

    print(f"[EDITOR] Área encontrada: {id_area}")
    print(f"[EDITOR] API CKEditor: {nome_editor or 'indisponível'}")

    if not html_original:
        raise RuntimeError("Editor retornou HTML vazio.")


    # 3. Localizar o parágrafo financeiro no HTML.
    soup = BeautifulSoup(html_original, "html.parser")

    paragrafos = [
        p for p in soup.find_all("p")
        if "Em atendimento ao despacho" in p.get_text(" ", strip=True)
        and "liquidação do BM" in p.get_text(" ", strip=True)
    ]

    if len(paragrafos) != 1:
        raise RuntimeError(
            f"Esperado 1 parágrafo financeiro; encontrados {len(paragrafos)}."
        )

    paragrafo = paragrafos[0]
    marcadores = paragrafo.find_all("strong")

    if len(marcadores) != 4:
        raise RuntimeError(
            f"Esperados 4 marcadores em negrito; "
            f"encontrados {len(marcadores)}."
        )

    # Validação para não alterar um documento já preenchido.
    textos = [m.get_text(" ", strip=True) for m in marcadores]

    if not (
        textos[0].startswith("XX")
        and textos[1] == "XX"
        and "X.XXX,XX" in textos[2]
        and textos[3] == "XXXXXXXXXX"
    ):
        raise RuntimeError(
            f"Marcadores diferentes do modelo esperado: {textos}"
        )

    # 4. Preencher os quatro marcadores mantendo o negrito.
    marcadores[0].string = f"{numero_solicitacao},"
    marcadores[1].string = numero_bm
    marcadores[2].string = (
        f"R$ {valor_formatado} ({valor_extenso})"
    )
    marcadores[3].string = fonte_completa

    # Retirar a indicação provisória de tipo de fonte.
    for trecho in paragrafo.find_all(string=True):
        if "(Tipo da Fonte Ex.: Tesouro do Estado)" in trecho:
            trecho.replace_with(
                str(trecho).replace(
                    "(Tipo da Fonte Ex.: Tesouro do Estado)", ""
                )
            )

    # Retirar os parênteses vazios após a solicitação.
    for trecho in paragrafo.find_all(string=True):
        texto = str(trecho)
        if re.search(r"\s*\(\s*\)", texto):
            trecho.replace_with(
                re.sub(r"\s*\(\s*\)", "", texto)
            )

    # 5. Preencher os dados superiores do despacho.
    for p in soup.find_all("p"):
        texto = p.get_text(" ", strip=True)

        if texto in ("Processo nº", "Processo nº:"):
            p.append(f": {numero_processo}" if ":" not in texto
                     else f" {numero_processo}")

        elif texto == "Despacho:":
            p.append(f" {numero_gop}")

    for trecho in soup.find_all(string=True):
        if "@nome_destinatario@" in trecho:
            trecho.replace_with(
                str(trecho).replace("@nome_destinatario@", "GAC")
            )

    # 6. Observação especial FINISA.
    if fonte == "0754006019":
        observacao = (
            "OBS: Precisa constar na Nota Fiscal o número do "
            "Contrato de Financiamento FINISA Nº 0655.144-00"
        )

        if observacao not in soup.get_text(" ", strip=True):
            novo_p = soup.new_tag("p")
            novo_strong = soup.new_tag("strong")
            novo_strong.string = observacao
            novo_p.append(novo_strong)
            paragrafo.insert_after(novo_p)

        print("[FINISA] Observação incluída.")

    novo_html = str(soup)

    
    # 7. Atualizar o conteúdo do editor.
    browser.set_script_timeout(30)

    if nome_editor:
        resultado = browser.execute_async_script("""
            const nome = arguments[0];
            const html = arguments[1];
            const concluir = arguments[arguments.length - 1];

            try {
                const editor = window.CKEDITOR?.instances?.[nome];

                if (!editor || typeof editor.setData !== 'function') {
                    concluir({
                        ok: false,
                        erro: "API do CKEditor indisponível"
                    });
                    return;
                }

                editor.setData(html, {
                    callback: function() {
                        editor.fire('change');
                        concluir({
                            ok: true,
                            html: editor.getData()
                        });
                    }
                });
            } catch (erro) {
                concluir({ok: false, erro: String(erro)});
            }
        """, nome_editor, novo_html)

    else:
        print("[EDITOR] Utilizando área contenteditable diretamente")

        resultado = browser.execute_script("""
            const id = arguments[0];
            const html = arguments[1];

            const area = document.getElementById(id);

            if (!area || area.getAttribute('contenteditable') !== 'true') {
                return {
                    ok: false,
                    erro: "Área editável não encontrada"
                };
            }

            area.focus();
            area.innerHTML = html;

            area.dispatchEvent(new InputEvent('input', {
                bubbles: true,
                inputType: 'insertReplacementText'
            }));

            area.dispatchEvent(new Event('change', {
                bubbles: true
            }));

            return {
                ok: true,
                html: area.innerHTML
            };
        """, id_area, novo_html)

    if not resultado or not resultado.get("ok"):
        raise RuntimeError(f"Falha no preenchimento: {resultado}")

    html_atual = resultado["html"]


    # 8. Validar o conteúdo realmente recebido pelo editor.
    html_atual = resultado["html"]
    texto_atual = BeautifulSoup(
        html_atual, "html.parser"
    ).get_text(" ", strip=True)

    obrigatorios = [
        numero_solicitacao,
        numero_bm,
        valor_formatado,
        fonte,
        numero_processo,
        numero_gop,
        "GAC",
    ]

    faltando = [
        valor for valor in obrigatorios
        if valor not in texto_atual
    ]

    if faltando:
        raise RuntimeError(
            f"Valores não confirmados no CKEditor: {faltando}"
        )

    if "X.XXX,XX" in texto_atual or "XXXXXXXXXX" in texto_atual:
        raise RuntimeError("Ainda existem valores provisórios no editor.")

    print("[EDITOR] CONTEÚDO PREENCHIDO E VALIDADO!")
    print("[EDITOR] Documento ainda NÃO foi salvo.")
    print("[PARADA] Confira visualmente os valores no Chrome.")

    return True


def diagnosticar_editor(browser, gop):
    """
    Diagnóstico SOMENTE DE LEITURA do editor SEI.
    Não altera, não salva e não fecha o documento.
    """

    print("\n" + "=" * 75)
    print("[DIAGNÓSTICO] INSPECIONANDO EDITOR DO GOP")
    print("=" * 75)

    browser.switch_to.default_content()

    print(f"[JANELA] Título: {browser.title}")
    print(f"[JANELA] URL: {browser.current_url}")
    print(f"[GOP] ID interno esperado: {gop['id_interno']}")

    parametros = parse_qs(urlparse(browser.current_url).query)
    id_aberto = parametros.get("id_documento", [""])[0]

    if id_aberto != str(gop["id_interno"]):
        raise RuntimeError(
            f"Editor incorreto: {id_aberto} != {gop['id_interno']}"
        )

    # Aguardar o conteúdo real do editor aparecer.
    def localizar_area(driver):
        return driver.execute_script("""
            const seletores = [
                '[id^="txaEditor_"][contenteditable="true"]',
                '[contenteditable="true"].cke_editable',
                '[contenteditable="true"][role="textbox"]'
            ];

            for (const seletor of seletores) {
                const elemento = document.querySelector(seletor);

                if (elemento && elemento.innerText.trim()) {
                    return {
                        id: elemento.id,
                        tag: elemento.tagName,
                        contenteditable:
                            elemento.getAttribute('contenteditable'),
                        texto: elemento.innerText,
                        html: elemento.innerHTML,
                        xpath: seletor
                    };
                }
            }

            return null;
        """)

    resultado = WebDriverWait(browser, 25).until(
        localizar_area
    )

    print(f"\n[EDITOR] ID: {resultado['id']}")
    print(f"[EDITOR] Tag: {resultado['tag']}")
    print(f"[EDITOR] Contenteditable: {resultado['contenteditable']}")
    print(f"[EDITOR] Seletor: {resultado['xpath']}")

    texto = resultado["texto"]
    html = resultado["html"]

    print("\n" + "=" * 75)
    print("[CONTEÚDO ORIGINAL DO CKEDITOR]")
    print("=" * 75)

    print(texto, flush=True)

    print("=" * 75)
    print(f"[EDITOR] Quantidade de caracteres: {len(texto)}")
    print(f"[EDITOR] Quantidade de caracteres HTML: {len(html)}")

    # Inspecionar especificamente o parágrafo financeiro.
    soup = BeautifulSoup(html, "html.parser")

    for indice, paragrafo in enumerate(soup.find_all("p"), start=1):
        texto_paragrafo = paragrafo.get_text(" ", strip=True)

        if "Em atendimento ao despacho" in texto_paragrafo:
            print("\n" + "=" * 75)
            print(f"[PARÁGRAFO FINANCEIRO] Posição: {indice}")
            print("=" * 75)

            print(texto_paragrafo)

            marcadores = paragrafo.find_all(["strong", "b"])

            print(f"\n[MARCADORES] Encontrados: {len(marcadores)}")

            for posicao, marcador in enumerate(marcadores, start=1):
                print(
                    f"[MARCADOR {posicao}] "
                    f"Texto: {marcador.get_text(' ', strip=True)!r}"
                )
                print(
                    f"[MARCADOR {posicao}] "
                    f"HTML: {str(marcador)}"
                )

            print("\n[HTML DO PARÁGRAFO FINANCEIRO]")
            print(str(paragrafo))

    # Diagnóstico da integração com CKEditor.
    info = browser.execute_script("""
        return {
            ckeditorExiste: typeof window.CKEDITOR !== 'undefined',
            instancesExiste: Boolean(
                window.CKEDITOR && window.CKEDITOR.instances
            ),
            editaveis: document.querySelectorAll(
                '[contenteditable="true"]'
            ).length,
            iframes: document.querySelectorAll('iframe').length
        };
    """)

    print("\n[ESTRUTURA DO EDITOR]")
    print(info)

    print("\n" + "=" * 75)
    print("[DIAGNÓSTICO CONCLUÍDO]")
    print("Nenhuma informação foi modificada.")
    print("Nenhum documento foi salvo.")
    print("=" * 75)

    return resultado


def inserir_link_solicitacao(browser, numero, link):
    """
    Seleciona o número da solicitação no editor,
    abre Ctrl+K e insere o acesso direto do SEI.
    """

    numero = str(numero).strip()
    link = str(link).strip()

    if not re.fullmatch(r"\d{8}", numero):
        raise RuntimeError("Número da solicitação inválido.")

    url = urlparse(link)

    if url.scheme != "https" or url.hostname != "sei.pe.gov.br":
        raise RuntimeError("Link não pertence ao SEI.")

    editor = WebDriverWait(browser, 20).until(
        EC.visibility_of_element_located((
            By.CSS_SELECTOR,
            '[id^="txaEditor_"][contenteditable="true"]'
        ))
    )

    # Seleciona exatamente os oito dígitos dentro do texto.
    selecionado = browser.execute_script("""
        const editor = arguments[0];
        const numero = arguments[1];
        const encontrados = [];
        const walker = document.createTreeWalker(
            editor, NodeFilter.SHOW_TEXT
        );

        let node;

        while ((node = walker.nextNode())) {
            const texto = node.textContent || "";
            let inicio = texto.indexOf(numero);

            while (inicio !== -1) {
                const antes = texto[inicio - 1] || "";
                const depois = texto[inicio + numero.length] || "";

                if (!/[0-9]/.test(antes) &&
                    !/[0-9]/.test(depois)) {
                    encontrados.push({
                        node: node,
                        inicio: inicio
                    });
                }

                inicio = texto.indexOf(
                    numero, inicio + numero.length
                );
            }
        }

        if (encontrados.length !== 1) {
            return encontrados.length;
        }

        const alvo = encontrados[0];
        const range = document.createRange();

        range.setStart(alvo.node, alvo.inicio);
        range.setEnd(
            alvo.node, alvo.inicio + numero.length
        );

        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);

        document.dispatchEvent(new Event("selectionchange"));

        return selection.toString() === numero ? 1 : 0;
    """, editor, numero)

    if selecionado != 1:
        raise RuntimeError(
            "Não foi possível selecionar exclusivamente "
            f"a solicitação {numero}. Ocorrências: {selecionado}"
        )

    print(f"Solicitação selecionada: {numero}")

    # Abre a ferramenta Link do CKEditor.
    from selenium.webdriver.common.action_chains import ActionChains

    ActionChains(browser).key_down(
        Keys.CONTROL
    ).send_keys(
        "k"
    ).key_up(
        Keys.CONTROL
    ).perform()

    print("Comando Ctrl+K executado.")

    # Localiza a caixa de link pela estrutura do CKEditor.
    # Não depende daquele ID dinâmico do XPath da imagem.
    painel = WebDriverWait(browser, 15).until(
        EC.visibility_of_element_located((
            By.CSS_SELECTOR,
            ".ck-balloon-panel.ck-balloon-panel_visible"
        ))
    )

    campos = [
        campo for campo in painel.find_elements(
            By.CSS_SELECTOR, "input:not([type='hidden'])"
        )
        if campo.is_displayed() and campo.is_enabled()
    ]

    
    # O painel possui dois campos:
    # 0 - Texto mostrado
    # 1 - URL do link

    if len(campos) != 2:
        raise RuntimeError(
            f"Estrutura inesperada do painel Link: "
            f"{len(campos)} campos."
        )

    campo_texto = campos[0]
    campo_url = campos[1]

    # Confirma que não vamos alterar o texto mostrado.
    texto_mostrado = (
        campo_texto.get_attribute("value") or ""
    ).strip()

    if texto_mostrado != numero:
        raise RuntimeError(
            f"Texto mostrado inesperado: {texto_mostrado!r}"
        )

    # Preenche somente o campo URL do link.
    campo_url.click()
    campo_url.send_keys(Keys.CONTROL, "a")
    campo_url.send_keys(link)

    if (campo_url.get_attribute("value") or "").strip() != link:
        raise RuntimeError(
            "O endereço não foi preenchido corretamente."
        )

    print("URL de acesso direto preenchida.")

    # Confirma o formulário com Enter.
    campo_url.send_keys(Keys.ENTER)

    print("Enter pressionado. Verificando hyperlink...")


    # Confirma o hyperlink no conteúdo editável.
    def conferir(driver):
        editor_atual = driver.find_element(
            By.CSS_SELECTOR,
            '[id^="txaEditor_"][contenteditable="true"]'
        )

        links = editor_atual.find_elements(
            By.TAG_NAME, "a"
        )

        correspondentes = [
            a for a in links
            if a.text.strip() == numero
            and a.get_attribute("href") == link
        ]

        return len(correspondentes) == 1

    WebDriverWait(browser, 15).until(conferir)

    print("Hiperlink confirmado no editor.")
    return True


def apagar_conteudo_e_salvar(browser, gop, mensagem, numero_solicitacao, link):
    """
    Apaga o conteúdo antigo, escreve a mensagem completa
    pelo teclado, valida e salva no SEI.
    """

    print("[ETAPA 5] Substituindo conteúdo do documento...")

    browser.switch_to.default_content()

    parametros = parse_qs(urlparse(browser.current_url).query)
    id_aberto = parametros.get("id_documento", [""])[0]

    if id_aberto != str(gop["id_interno"]):
        raise RuntimeError(
            f"GOP incorreto: {id_aberto} != {gop['id_interno']}"
        )

    seletor = '[id^="txaEditor_"][contenteditable="true"]'

    editor = WebDriverWait(browser, 20).until(
        EC.element_to_be_clickable((
            By.CSS_SELECTOR,
            seletor
        ))
    )

    print(f"[EDITOR] Localizado: {editor.get_attribute('id')}")

    # 1. Apaga todo o conteúdo anterior.
    
    # 1. Preservar Atenciosamente e toda a assinatura.
    
    resultado_assinatura = browser.execute_script(r"""
        const editor = arguments[0];

        // Procura Atenciosamente em qualquer nó de texto,
        // mesmo que esteja dentro de table, td, span ou p.
        const walker = document.createTreeWalker(
            editor,
            NodeFilter.SHOW_TEXT
        );

        const encontrados = [];
        let no;

        while ((no = walker.nextNode())) {
            const texto = (no.textContent || "").trim();

            if (/^Atenciosamente\s*,?/i.test(texto)) {
                encontrados.push(no);
            }
        }

        if (encontrados.length !== 1) {
            return {
                ok: false,
                erro: "Marcador Atenciosamente não identificado",
                quantidade: encontrados.length
            };
        }

        // Sobe pela estrutura HTML até encontrar
        // o bloco que é filho direto do editor.
        let bloco = encontrados[0].parentElement;

        while (
            bloco &&
            bloco.parentElement !== editor
        ) {
            bloco = bloco.parentElement;
        }

        if (!bloco || bloco.parentElement !== editor) {
            return {
                ok: false,
                erro: "Bloco da assinatura fora do editor"
            };
        }

        // Não permite apagar parte de um bloco
        // que também contenha outros textos.
        const textoBloco = (
            bloco.innerText || bloco.textContent || ""
        ).trim();

        if (!/^Atenciosamente\s*,?/i.test(textoBloco)) {
            return {
                ok: false,
                erro: "Bloco começa antes de Atenciosamente",
                inicio: textoBloco.slice(0, 100)
            };
        }

        const conteudo = editor.innerText || "";
        const marcador = /Atenciosamente\s*,?/i.exec(conteudo);

        if (!marcador) {
            return {
                ok: false,
                erro: "Assinatura não encontrada no texto"
            };
        }

        const anterior = conteudo.slice(0, marcador.index);
        const assinatura = conteudo.slice(marcador.index).trim();

        if (
            !anterior.includes("X.XXX,XX") ||
            !anterior.includes("XXXXXXXXXX")
        ) {
            return {
                ok: false,
                erro: "Documento não contém o modelo original"
            };
        }

        if (assinatura.length < 25) {
            return {
                ok: false,
                erro: "Assinatura original incompleta"
            };
        }

        // Seleciona do início do editor até
        // imediatamente ANTES do bloco Atenciosamente.
        editor.focus();

        const range = document.createRange();
        range.setStart(editor, 0);
        range.setEndBefore(bloco);

        const selecao = window.getSelection();
        selecao.removeAllRanges();
        selecao.addRange(range);

        if (selecao.isCollapsed) {
            return {
                ok: false,
                erro: "Seleção vazia"
            };
        }

        return {
            ok: true,
            assinatura: assinatura,
            bloco: bloco.tagName,
            selecionado: selecao.toString().slice(0, 100)
        };
    """, editor)


    if not resultado_assinatura.get("ok"):
        raise RuntimeError(
            "Não foi possível preservar a assinatura: "
            f"{resultado_assinatura}"
        )

    assinatura_original = resultado_assinatura["assinatura"]

    # Apaga somente a seleção anterior à assinatura.
    from selenium.webdriver.common.action_chains import ActionChains

    ActionChains(browser).send_keys(
        Keys.BACKSPACE
    ).perform()

    editor = browser.find_element(By.CSS_SELECTOR, seletor)

    def normalizar_assinatura(texto):
        return re.sub(r"\s+", " ", texto).strip()

    restante = editor.get_attribute("innerText") or ""

    if (
        normalizar_assinatura(restante) !=
        normalizar_assinatura(assinatura_original)
    ):
        raise RuntimeError(
            "A assinatura original foi modificada "
            "durante a limpeza. Salvamento bloqueado."
        )

    print("[EDITOR] Conteúdo anterior apagado.")
    print("[EDITOR] Assinatura original preservada.")


    # 2. Escreve a mensagem pronta pelo teclado.
        # 2. Escrever antes de Atenciosamente.
    print("[EDITOR] Inserindo mensagem financeira...")

    browser.execute_script("""
        const editor = arguments[0];

        const range = document.createRange();
        range.setStart(editor, 0);
        range.collapse(true);

        editor.focus();

        const selecao = window.getSelection();
        selecao.removeAllRanges();
        selecao.addRange(range);
    """, editor)

    # Identifica os três valores dentro da mensagem montada.
    padrao = (
        r"liquidação do BM\s+(?P<bm>[^,\n]+),"
        r"\s+no valor de\s+(?P<valor>R\$\s*[\d.,]+),"
        r"\s+na Fonte de Recursos\s+"
        r"(?P<fonte>\d{10}(?:\s*/\s*\d{10})*)"
        r"\s+\("
    )

    correspondencia = re.search(padrao, mensagem)

    if not correspondencia:
        raise RuntimeError(
            "Não foi possível identificar BM, valor e fonte "
            "na mensagem. Inserção interrompida."
        )

    trechos = [
        correspondencia.span("bm"),
        correspondencia.span("valor"),
        correspondencia.span("fonte"),
    ]

    # Destaca as observações FINISA, quando presentes.
    observacoes = [
        (
            "OBS: Precisa constar na Nota Fiscal o número "
            "do Contrato de Financiamento FINISA "
            "Nº 0655.144-00"
        )
    ]

    for observacao in observacoes:
        inicio = mensagem.find(observacao)

        if inicio >= 0:
            trechos.append((
                inicio,
                inicio + len(observacao)
            ))

    # Garante que a digitação siga a ordem do documento.
    trechos.sort(key=lambda trecho: trecho[0])

    posicao = 0

    for inicio, fim in trechos:
        # Insere texto normal até o próximo valor.
        if inicio > posicao:
            ActionChains(browser).send_keys(
                mensagem[posicao:inicio]
            ).perform()

        # Liga negrito, escreve o valor e desliga negrito.
        ActionChains(browser).key_down(
            Keys.CONTROL
        ).send_keys("b").key_up(
            Keys.CONTROL
        ).perform()
        ActionChains(browser).send_keys(
            mensagem[inicio:fim]
        ).perform()

        ActionChains(browser).key_down(
            Keys.CONTROL
        ).send_keys("b").key_up(
            Keys.CONTROL
        ).perform()

        posicao = fim

    # Insere o restante da mensagem normalmente.
    if posicao < len(mensagem):
        ActionChains(browser).send_keys(
            mensagem[posicao:]
        ).perform()

    print("[EDITOR] BM, valor e fonte inseridos em negrito.")


    time.sleep(2)

    # 3. Valida o texto depois de perder o foco.
    editor = browser.find_element(By.CSS_SELECTOR, seletor)

    texto_atual = (
        editor.get_attribute("innerText") or ""
    )

    def normalizar(texto):
        return re.sub(r"\s+", " ", texto).strip()

    esperado = normalizar(
        mensagem + "\n\n" + assinatura_original
    )
    recebido = normalizar(texto_atual)

    if esperado != recebido:
        print("[EDITOR] TEXTO ESPERADO:")
        print(esperado)
        print("[EDITOR] TEXTO ENCONTRADO:")
        print(recebido)

        raise RuntimeError(
            "A mensagem não foi inserida integralmente."
        )

    print("[EDITOR] Mensagem inserida integralmente.")

    # 4. Confere se o editor mantém o conteúdo.
    browser.find_element(By.TAG_NAME, "body").click()
    time.sleep(2)

    editor = browser.find_element(By.CSS_SELECTOR, seletor)

    texto_apos_foco = (
        editor.get_attribute("innerText") or ""
    )

    if normalizar(texto_apos_foco) != esperado:
        raise RuntimeError(
            "O editor restaurou o conteúdo após perder o foco."
        )

    print("[EDITOR] Texto permaneceu após perder o foco.")

    # Insere o acesso direto na referência à solicitação.
    inserir_link_solicitacao(
        browser,
        numero_solicitacao,
        link
    )

    # 5. Procura o botão Salvar.
    botoes = browser.find_elements(
        By.XPATH,
        '//*[@title="Salvar" or @aria-label="Salvar" '
        'or normalize-space(text())="Salvar"]'
    )

    botoes = [
        botao for botao in botoes
        if botao.is_displayed() and botao.is_enabled()
    ]

    if len(botoes) != 1:
        raise RuntimeError(
            f"Esperado 1 botão Salvar; encontrados {len(botoes)}."
        )

    print("[ETAPA 6] Salvando documento...")

    botoes[0].click()
    time.sleep(3)

    print("[SALVAR] Botão Salvar acionado.")

    # 6. Confirma pela leitura após recarregar a janela.
    browser.refresh()

    editor = WebDriverWait(browser, 25).until(
        EC.presence_of_element_located((
            By.CSS_SELECTOR,
            seletor
        ))
    )

    texto_salvo = (
        editor.get_attribute("innerText") or ""
    )

    if normalizar(texto_salvo) != esperado:
        raise RuntimeError(
            "Conteúdo não confirmado após recarregar o editor."
        )

    print("[SALVAR] Conteúdo confirmado após recarregar.")
    editor = browser.find_element(
        By.CSS_SELECTOR,
        '[id^="txaEditor_"][contenteditable="true"]'
    )

    links_salvos = [
        a for a in editor.find_elements(By.TAG_NAME, "a")
        if a.text.strip() == str(numero_solicitacao)
        and a.get_attribute("href") == link
    ]

    if len(links_salvos) != 1:
        raise RuntimeError(
            "O texto foi salvo, mas o hyperlink "
            "da solicitação não foi confirmado."
        )

    print("Link da solicitação confirmado após salvar.")
    print(f"[GOP] Documento: {gop['numero_sei']}")
    print("[TESTE CONCLUÍDO] Mensagem gravada no editor.")
    print("[PARADA] Não assina e não atualiza a planilha.")

    return True


def montar_mensagem_gop(dados, numero_solicitacao, numero_gop):
    """
    Monta a mensagem completa a partir da planilha.
    Não interage com o navegador.
    """

    colunas = dados["linha_completa"]

    if len(colunas) < 15:
        raise ValueError("Linha sem colunas suficientes.")

    processo = str(dados["numero_sei"]).strip()
    solicitacao = str(numero_solicitacao).strip()
    numero_gop = str(numero_gop).strip()
    bm = str(colunas[13]).strip()

    # Valor da coluna RESOLUÇÃO da planilha.
    resolucao = str(dados.get("resolucao") or "").strip()

    if not resolucao:
        raise ValueError(
            "Coluna RESOLUÇÃO vazia para este SEI. "
            "Não será gerado um documento incompleto."
        )

    if not re.fullmatch(r"\d{8}", numero_gop):
        raise RuntimeError(
            "Número do GOP criado não identificado corretamente."
        )

    valor_original = str(colunas[14]).strip()
    valor_limpo = (
        valor_original.replace("R$", "")
        .replace(" ", "")
        .replace(".", "")
        .replace(",", ".")
    )

    try:
        valor_decimal = Decimal(valor_limpo).quantize(
            Decimal("0.01")
        )
    except InvalidOperation:
        raise ValueError(
            f"Valor financeiro inválido: {valor_original}"
        )

    if valor_decimal <= 0:
        raise ValueError("Valor financeiro deve ser positivo.")

    valor = (
        f"{valor_decimal:,.2f}"
        .replace(",", "#")
        .replace(".", ",")
        .replace("#", ".")
    )

        # Verifica a coluna FONTE (AE) da planilha.
    
    # Verificar a coluna AE (FONTE) da planilha.
    # Índice 30 corresponde à coluna AE.

    fonte_ae = (
        str(colunas[30]).strip()
        if len(colunas) > 30
        else ""
    )

    fonte_registro = str(
        dados.get("fonte", "")
    ).strip()

    # Considera tanto o valor exibido na planilha
    # quanto o valor convertido por get_all_records().
    fontes_planilha = f"{fonte_ae}\n{fonte_registro}"

    codigos_fonte = {
        codigo.zfill(10)
        for codigo in re.findall(
            r"(?<!\d)\d{9,10}(?!\d)",
            fontes_planilha
        )
    }

    if not codigos_fonte:
        raise RuntimeError(
            "Nenhum código de FONTE identificado na "
            "coluna AE. Documento não será gerado."
        )

    tem_finisa = "0754006019" in codigos_fonte

    # Fonte de Recursos: códigos da coluna AE.
    fonte = " / ".join(sorted(codigos_fonte))

    # Conteúdo dos parênteses: Ficha Financeira (AH).
    ficha_financeira = str(
        dados.get("ficha_financeira") or ""
    ).strip()

    if not ficha_financeira:
        raise ValueError(
            "Ficha Financeira (AH) vazia. "
            "Não será gerado documento incompleto."
        )

    print("[FONTE] Valor da coluna AE:", repr(fonte_ae))
    print("[FONTE] Códigos identificados:", sorted(codigos_fonte))
    print(
        "[FINISA] Regra aplicada:",
        "SIM" if tem_finisa else "NÃO"
    )


    observacao_finisa = ""

    if tem_finisa:
        observacao_finisa = (
            "OBS: Precisa constar na Nota Fiscal o número "
            "do Contrato de Financiamento FINISA "
            "Nº 0655.144-00\n\n"
        )

    if not processo or not solicitacao or not bm or not fonte:
        raise ValueError(
            "Processo, solicitação, BM ou fonte não informados."
        )

    if (processo != SEI_ALVO or not re.fullmatch(r"\d{8}", solicitacao)):
        raise RuntimeError(
            "Processo ou solicitação diferentes do teste."
        )

    mensagem = (
        "DISPONIBILIDADE FINANCEIRA - GOP\n\n"
        "CEHAB - DISPONIBILIDADE FINANCEIRA - GOP\n\n"
        f"Processo nº: {processo}\n\n"
        f"Despacho: {numero_gop}\n\n"
        "Destinatário: GAC\n\n"
        f"Em atendimento ao despacho {solicitacao}, "
        "informo que há disponibilidade orçamentária "
        "e financeira para liquidação do "
        f"BM {bm}, no valor de R$ {valor}, "
        f"na Fonte de Recursos {fonte} "
        f"({ficha_financeira}).\n\n"
        f"{observacao_finisa}"
        f"{'-' * 150}\n\n"
        "À GEFIN,\n\n"
        f"{resolucao}\n\n"
    )
        
    print("[MENSAGEM] Processo:", processo)
    print("[MENSAGEM] Solicitação:", solicitacao)
    print("[MENSAGEM] BM:", bm)
    print("[MENSAGEM] Valor: R$", valor)
    print("[MENSAGEM] Fonte:", fonte)
    print("\n[MENSAGEM COMPLETA]\n")
    print(mensagem)

    return mensagem


def capturar_link_solicitacao(browser, solicitacao):
    """
    Captura o número e o Link para Acesso Direto
    diretamente dos atributos do menu da solicitação.

    Não clica no menu nem utiliza o clipboard.
    """

    numero = str(solicitacao["numero"]).strip()
    id_interno = str(solicitacao["id_interno"]).strip()

    if not re.fullmatch(r"\d{8}", numero):
        raise RuntimeError("Número da solicitação inválido.")

    if not id_interno.isdigit():
        raise RuntimeError("ID interno inválido.")

    browser.switch_to.default_content()

    try:
        WebDriverWait(browser, 20).until(
            EC.frame_to_be_available_and_switch_to_it(
                (By.ID, "ifrArvore")
            )
        )

        # Confirma qual documento estamos consultando.
        ancora = WebDriverWait(browser, 15).until(
            EC.presence_of_element_located(
                (By.ID, f"anchor{id_interno}")
            )
        )

        texto = normalizar_texto(ancora.text)

        if (
            "SOLICITACAO DE DISPONIBILIDADE FINANCEIRA"
            not in texto
            or numero not in re.findall(
                r"(?<!\d)\d{8}(?!\d)", texto
            )
        ):
            raise RuntimeError(
                "A âncora não corresponde à solicitação."
            )

        # Menu associado exclusivamente a essa solicitação.
        menu = WebDriverWait(browser, 15).until(
            EC.presence_of_element_located((
                By.ID,
                f"popover-contentanchorImg{id_interno}"
            ))
        )

        # 1. Identificar o número do documento.
        numeros = menu.find_elements(
            By.CSS_SELECTOR,
            'a[tipo="texto"][data-clipboard-text]'
        )

        numeros_corretos = [
            opcao for opcao in numeros
            if (
                opcao.get_attribute("data-clipboard-text")
                or ""
            ).strip() == numero
        ]

        if len(numeros_corretos) != 1:
            raise RuntimeError(
                "Número da solicitação não encontrado "
                "de maneira única no menu."
            )

        print("Número do documento capturado:", numero)

        # 2. Identificar Link para Acesso Direto.
        opcoes_link = menu.find_elements(
            By.CSS_SELECTOR,
            'a[tipo="url"][data-clipboard-text]'
        )

        if len(opcoes_link) != 1:
            raise RuntimeError(
                "Link para Acesso Direto não encontrado "
                "de maneira única."
            )

        opcao_link = opcoes_link[0]

        # O menu pode estar oculto no DOM do iframe.
        # Por isso, não utilizamos .text para validar a opção.

        tipo_opcao = (
            opcao_link.get_attribute("tipo") or ""
        ).strip().lower()

        if tipo_opcao != "url":
            raise RuntimeError(
                "A opção encontrada não é do tipo URL."
            )

        link = (
            opcao_link.get_attribute("data-clipboard-text")
            or ""
        ).strip()

        # 3. Validar o endereço antes de usar no GOP.
        url = urlparse(link)
        parametros = parse_qs(url.query)

        if (
            url.scheme != "https"
            or url.hostname != "sei.pe.gov.br"
            or url.path != "/sei/controlador.php"
        ):
            raise RuntimeError(
                "O acesso direto não pertence ao SEI."
            )

        if parametros.get("acao", [""])[0] != (
            "procedimento_trabalhar"
        ):
            raise RuntimeError(
                "Ação inesperada no acesso direto."
            )

        id_documento_link = parametros.get(
            "id_documento", [""]
        )[0]

        if id_documento_link != id_interno:
            raise RuntimeError(
                "O link aponta para outro documento."
            )

        # Confirma que o processo também corresponde.
        url_arvore = urlparse(
            ancora.get_attribute("href") or ""
        )

        parametros_arvore = parse_qs(url_arvore.query)

        id_processo_arvore = parametros_arvore.get(
            "id_procedimento", [""]
        )[0]

        id_processo_link = parametros.get(
            "id_procedimento", [""]
        )[0]

        if (
            not id_processo_arvore
            or id_processo_arvore != id_processo_link
        ):
            raise RuntimeError(
                "O link aponta para outro processo."
            )

        # 4. Entregar as variáveis ao restante do robô.
        solicitacao["link_direto"] = link

        print("Link para Acesso Direto capturado.")
        print("Referência do documento confirmada.")

        return link

    finally:
        browser.switch_to.default_content()


def fechar_menu_solicitacao(browser, solicitacao):
    """Fecha o popover, se ainda aberto, sem alterar a seleção do processo."""
    browser.switch_to.default_content()
    browser.switch_to.frame(browser.find_element(By.ID, "ifrArvore"))
    try:
        menu_id = f"popover-contentanchorImg{solicitacao['id_interno']}"
        menus = browser.find_elements(By.ID, menu_id)
        if menus and menus[0].is_displayed():
            fechar = menus[0].find_elements(
                By.XPATH, ".//*[normalize-space(.)='Fechar']"
            )
            if fechar:
                browser.execute_script("arguments[0].click();", fechar[-1])
            else:
                # Clicar na própria âncora, sem navegar, para fechar o popover.
                icone = browser.find_elements(By.ID, f"anchorImg{solicitacao['id_interno']}")
                if icone:
                    browser.execute_script("arguments[0].click();", icone[0])
        WebDriverWait(browser, 5).until(
            lambda b: not any(m.is_displayed() for m in b.find_elements(By.ID, menu_id))
        )
    finally:
        browser.switch_to.default_content()


def verificar_sem_editor_pendente(browser):
    """Evita associar a criação atual com popup editor_montar de teste anterior."""
    atual = browser.current_window_handle
    try:
        for handle in browser.window_handles:
            browser.switch_to.window(handle)
            if "acao=editor_montar" in browser.current_url:
                raise RuntimeError(
                    "Há editor do SEI aberto de outra execução. "
                    "Feche-o manualmente antes de criar um novo GOP."
                )
    finally:
        browser.switch_to.window(atual)
        browser.switch_to.default_content()


# Configuração de segurança para este teste: apenas localizar e capturar.
# Alterar para False SOMENTE quando a etapa de leitura estiver validada
# e a existência de GOP anterior tiver sido conferida manualmente.
TESTE_SOMENTE_LEITURA = False

# Saída concisa no terminal; os logs completos vão para este arquivo.
LOG_DETALHADO = os.path.join(BASE_DIR, "despacho_diagnostico.log")


def executar_discreto(funcao, *args, **kwargs):
    """Preserva os logs internos no arquivo sem poluir o terminal."""
    from contextlib import redirect_stdout
    with open(LOG_DETALHADO, "a", encoding="utf-8") as arquivo:
        with redirect_stdout(arquivo):
            return funcao(*args, **kwargs)


def validar_processo_atual(browser):
    """Confirma o número do processo na árvore antes de qualquer operação."""
    browser.switch_to.default_content()
    WebDriverWait(browser, 25).until(
        EC.presence_of_element_located((By.ID, "ifrArvore"))
    )
    browser.switch_to.frame("ifrArvore")
    try:
        WebDriverWait(browser, 25).until(
            lambda driver: any(
                el.text.strip() == SEI_ALVO
                for el in driver.find_elements(By.TAG_NAME, "a")
            )
        )
    finally:
        browser.switch_to.default_content()


def obter_gop_pos_criacao(
    browser, principal, gops_antes, limite=30
):
    """
    Identifica somente um GOP novo na árvore.

    Se o editor automático tiver aberto,
    fecha apenas a janela do GOP confirmado.

    Se não tiver aberto, continua normalmente.
    """

    gop = None
    inicio = time.monotonic()

    while time.monotonic() - inicio < limite:
        browser.switch_to.window(principal)

        gops_depois = localizar_gops_na_arvore(browser)

        novos_ids = set(gops_depois) - set(gops_antes)

        if len(novos_ids) > 1:
            raise RuntimeError(
                "Mais de um GOP apareceu na árvore. "
                "Execução interrompida para revisão."
            )

        if len(novos_ids) == 1:
            id_novo = novos_ids.pop()
            gop = gops_depois[id_novo]
            break

        time.sleep(1)

    if not gop:
        raise RuntimeError(
            "Nenhum GOP novo foi identificado. "
            "Confira o processo antes de repetir."
        )

    print(f"GOP criado: {gop['numero_sei']}")

    # O editor automático agora é opcional.
    for handle in list(browser.window_handles):
        if handle == principal:
            continue

        browser.switch_to.window(handle)
        browser.switch_to.default_content()

        url = urlparse(browser.current_url)
        parametros = parse_qs(url.query)

        acao = parametros.get("acao", [""])[0]
        id_documento = parametros.get(
            "id_documento", [""]
        )[0]

        if (
            acao == "editor_montar"
            and id_documento == gop["id_interno"]
        ):
            print("Fechando editor automático do GOP.")
            browser.close()
            break

    browser.switch_to.window(principal)
    browser.switch_to.default_content()

    print("GOP identificado na árvore.")
    print("Prosseguindo para Editar Conteúdo.")

    return gop



def localizar_gops_na_arvore(browser):
    """
    Retorna todos os GOPs da árvore, identificados
    pelo ID interno e pelo número público do SEI.
    Não seleciona nenhum documento.
    """
    browser.switch_to.default_content()

    frame = WebDriverWait(browser, 20).until(
        EC.presence_of_element_located(
            (By.ID, "ifrArvore")
        )
    )

    browser.switch_to.frame(frame)

    gops = {}

    try:
        for link in browser.find_elements(
            By.CSS_SELECTOR, "a[id^='anchor']"
        ):
            texto = normalizar_texto(link.text)

            if (
                "CEHAB - DISPONIBILIDADE FINANCEIRA - GOP"
                not in texto
            ):
                continue

            id_anchor = link.get_attribute("id") or ""
            correspondencia = re.fullmatch(
                r"anchor(\d+)", id_anchor
            )

            numeros = re.findall(
                r"(?<!\d)\d{8}(?!\d)",
                texto
            )

            if not correspondencia or len(numeros) != 1:
                raise RuntimeError(
                    f"GOP com identificação incompleta: {texto}"
                )

            id_interno = correspondencia.group(1)

            gops[id_interno] = {
                "id_interno": id_interno,
                "numero_sei": numeros[0]
            }

    finally:
        browser.switch_to.default_content()

    return gops



def executar_teste():
    print("=" * 72)
    print("SEIs EM MONITORAMENTO")
    print(f"Processo: {SEI_ALVO}")
    print("=" * 72)

    browser = None
    houve_criacao = False
    try:
        registros = executar_discreto(obter_aguardando_sei)
        linhas = [d for d in registros if str(d["numero_sei"]).strip() == SEI_ALVO]
        if len(linhas) != 1:
            raise RuntimeError(
                f"Verificar Status do SEI"
            )

        browser = executar_discreto(iniciar_robo)
        print(f"Verificando: {SEI_ALVO}")

        browser.switch_to.default_content()
        acao = parse_qs(urlparse(browser.current_url).query).get("acao", [""])[0]

        if acao == "procedimento_controlar":
            if not executar_discreto(verificar_recebidos, browser, SEI_ALVO):
                raise RuntimeError("Processo não encontrado no Controle de Processos.")
        elif acao != "procedimento_trabalhar":
            raise RuntimeError("Abra o SEI autenticado em Controle de Processos ou no processo-alvo.")

        validar_processo_atual(browser)
        solicitacoes = executar_discreto(listar_solicitacoes, browser)
        lotes = executar_discreto(preparar_lotes, linhas, solicitacoes, browser)
        if len(lotes) != 1:
            raise RuntimeError("Solicitação não identificada de maneira única; revisão manual necessária.")

        solicitacao = lotes[0]["solicitacao"]
        print(f"Encontrou solicitação de disponibilidade: {solicitacao['texto']}")
        print(f"Número: {solicitacao['numero']}")

        link = executar_discreto(capturar_link_solicitacao, browser, solicitacao)
        if not link:
            raise RuntimeError("Link de acesso direto não foi confirmado.")
        print("Link Copiado")  # o acesso direto foi capturado do SEI
        # Encerrar o menu contextual aberto pela captura do link antes de criar o GOP.
        executar_discreto(fechar_menu_solicitacao, browser, solicitacao)

        if TESTE_SOMENTE_LEITURA:
            print("Teste finalizado: nenhuma criação ou alteração de GOP.")
            return

        # Fluxo completo: preserva as funções de criação e edição existentes.
        if not executar_discreto(conferir_responsavel, linhas):
            raise RuntimeError("Responsável não confirmado.")
        print("Gerando documento CEHAB - DISPONIBILIDADE FINANCEIRA - GOP...")
        # Evita capturar um editor antigo ainda aberto no Chrome.
        executar_discreto(verificar_sem_editor_pendente, browser)
        
        principal = executar_discreto(
            janela_principal_sei, browser
        )

        # Registra todos os GOPs existentes ANTES da criação.
        gops_antes = executar_discreto(
            localizar_gops_na_arvore, browser
        )

        executar_discreto(
            mostrar_criacao,
            browser,
            SEI_ALVO,
            solicitacao["numero"]
        )

        houve_criacao = True

        numero = executar_discreto(
            criar_documento,
            browser,
            linhas[0],
            solicitacao
        )

        if numero != solicitacao["numero"]:
            raise RuntimeError(
                "Criação não confirmada. "
                "Confira no SEI antes de repetir."
            )

        print("Documento solicitado.")

        # Identifica o GOP novo sem depender do editor automático.
        gop = executar_discreto(
            obter_gop_pos_criacao,
            browser,
            principal,
            gops_antes,
            limite=30
        )

        executar_discreto(selecionar_gop_recem_criado, browser, gop["id_interno"], gop["numero_sei"])
        executar_discreto(clicar_editar_conteudo, browser, gop["id_interno"])
        print("Editor de conteúdo aberto")
        mensagem = executar_discreto(
            montar_mensagem_gop,
            linhas[0],
            solicitacao["numero"],
            gop["numero_sei"]
        )
        print("Inserindo mensagem financeira da planilha...")
        executar_discreto(
            apagar_conteudo_e_salvar,
            browser,
            gop,
            mensagem,
            solicitacao["numero"],
            link
        )

        print(f"GOP salvo: {gop['numero_sei']}")

        # Fecha somente a janela correta do editor.
        parametros = parse_qs(urlparse(browser.current_url).query)

        if (
            parametros.get("acao", [""])[0] != "editor_montar"
            or parametros.get("id_documento", [""])[0]
            != str(gop["id_interno"])
        ):
            raise RuntimeError(
                "Janela do editor não corresponde ao GOP esperado."
            )

        browser.close()
        browser.switch_to.window(principal)
        browser.switch_to.default_content()

        print("Editor fechado. Processo SEI permanece aberto.")

        # =====================================================
        # ATUALIZAR STATUS NA PLANILHA
        # Executar somente após salvar e fechar o GOP.
        # =====================================================

        print("Atualizando status na planilha de BMs...")

        executar_discreto(
            atualizar_status_apos_gop,
            linhas[0],
            gop["numero_sei"]
        )

        print("Processamento finalizado com sucesso.")

    except Exception as erro:
        print(f"Erro: {erro}")
        with open(LOG_DETALHADO, "a", encoding="utf-8") as arquivo:
            arquivo.write("\n--- ERRO ---\n")
            traceback.print_exc(file=arquivo)
        if houve_criacao:
            print("Atenção: o GOP pode ter sido criado. Confira antes de repetir.")
        print(f"Diagnóstico detalhado: {LOG_DETALHADO}")
    finally:
        if browser is not None:
            try:
                browser.switch_to.default_content()
            except Exception:
                pass
        print("Chrome NUPCO mantido aberto.")


if __name__ == "__main__":
    executar_teste()
