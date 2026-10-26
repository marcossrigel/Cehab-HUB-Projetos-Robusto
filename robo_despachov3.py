import os

import gspread

import re

import time

import sys

import unicodedata

from urllib.parse import urlparse, parse_qs

from num2words import num2words

from dotenv import load_dotenv

from selenium.common.exceptions import UnexpectedAlertPresentException

from selenium.webdriver.common.alert import Alert
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

from seleniumbase import Driver

from selenium.webdriver.support.ui import WebDriverWait

from selenium.webdriver.support import expected_conditions as EC

from oauth2client.service_account import ServiceAccountCredentials

from selenium.webdriver.common.by import By

from datetime import datetime
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from html import escape as escapar_html

ABA = "BMs 2026"

if getattr(sys, "frozen", False):

    BASE_DIR = os.path.dirname(sys.executable)

else:

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CREDENCIAIS_GOOGLE = os.path.join(

    BASE_DIR,

    "arquivos_json",

    "credenciais_sheets.json"

)

ENV_PATH = os.path.join(

    BASE_DIR,

    "arquivos_json",

    "arquivo.env"

)

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


def atualizar_planilha_enviado(linhas_planilha):
    linhas = sorted(set(int(n) for n in linhas_planilha))
    if not linhas:
        return

    worksheet = conectar_planilha()
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    atualizacoes = []

    for linha in linhas:
        atualizacoes.append({
            "range": f"Z{linha}:AB{linha}",
            "values": [["AGUARDANDO ASSINATURA", "GAC", data_hoje]]
        })

    worksheet.batch_update(
        atualizacoes,
        value_input_option="USER_ENTERED"
    )

    print(f"PLANILHA ATUALIZADA: linhas {linhas}")


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

def iniciar_robo():

    load_dotenv(ENV_PATH)

    usuario = os.getenv(

        "SEI_USER"

    )

    senha = os.getenv(

        "SEI_PASS"

    )

    browser = Driver(

        uc=False,

        headless=True,

        log_cdp=False

    )

    browser.get(

        "https://sei.pe.gov.br/sip/login.php?sigla_orgao_sistema=GOVPE&sigla_sistema=SEI"

    )

    browser.sleep(3)

    browser.find_element(

        "css selector",

        "#selOrgao"

    ).send_keys(

        "CEHAB"

    )

    browser.find_element(

        "xpath",

        '//*[@id="txtUsuario"]'

    ).send_keys(

        usuario

    )

    browser.find_element(

        "xpath",

        '//*[@id="pwdSenha"]'

    ).send_keys(

        senha

    )

    browser.find_element(

        "xpath",

        '//*[@id="sbmAcessar"]'

    ).click()

    browser.sleep(5)

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

                print(

                    f"{numero_sei} ENCONTRADO"

                )

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

                browser.sleep(5)

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

    browser.switch_to.default_content()

    browser.switch_to.frame(

        browser.find_element(By.ID, "ifrArvore")

    )

    solicitacoes = []

    for link in browser.find_elements(By.TAG_NAME, "a"):

        texto = link.text.strip()

        if "CEHAB - SOLICITAÇÃO DE DISPONIBILIDADE FINANCEIRA" not in texto.upper():

            continue

        numero = re.search(r"(\d{8})\)?\s*$", texto)

        if numero:

            solicitacoes.append({

                "texto": texto,

                "numero": numero.group(1),

            })

    browser.switch_to.default_content()

    return solicitacoes

def agrupar_por_sei(lista):
    """Uma entrada por número SEI, preservando as linhas em ordem."""
    agrupados = defaultdict(list)
    for dados in lista:
        numero = str(dados["numero_sei"]).strip()
        if not numero:
            print(f"LINHA {dados['linha_planilha']} SEM NÚMERO SEI: ignorada")
            continue
        agrupados[numero].append(dados)
    return dict(agrupados)


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


def existe_gop_no_processo(browser):
    """Trava conservadora: havendo GOP existente, exige revisão antes de recriar."""
    ids = listar_ids_gop(browser)
    if ids:
        print(f"JÁ EXISTE(M) DESPACHO(S) GOP NO PROCESSO: {sorted(ids)}")
        print("PROCESSAMENTO INTERROMPIDO PARA EVITAR DESPACHO DUPLICADO")
        return True
    return False


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
        browser.sleep(3)

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

        print("BOTÃO INCLUIR DOCUMENTO CLICADO")

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

        print("IFRAME DE VISUALIZAÇÃO LOCALIZADO")


        documento_gop = browser.find_element(

            "xpath",

            '//*[@id="tblSeries"]/tbody/tr[2]/td/a[2]'

        )

        browser.execute_script(

            "arguments[0].click();",

            documento_gop

        )

        browser.sleep(5)

        campo_destinatario = browser.find_element(

            "id",

            "txtDestinatario"

        )

        campo_destinatario.send_keys(

            "GAC"

        )

        browser.sleep(1)

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

            browser.sleep(1)

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

            browser.sleep(2)

            campo_interessado.send_keys(

                Keys.ARROW_DOWN

            )

            browser.sleep(1)

            campo_interessado.send_keys(

                Keys.ENTER

            )

            browser.sleep(2)

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

        browser.sleep(1)

        botao_salvar = browser.find_element(

            "id",

            "btnSalvar"

        )

        browser.execute_script(

            "arguments[0].click();",

            botao_salvar

        )

        browser.sleep(5)

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

def capturar_id_documento(browser, ids_anteriores):

    try:

        ids_novos = listar_ids_gop(browser) - ids_anteriores

        if len(ids_novos) != 1:

            print(

                "NÃO FOI POSSÍVEL IDENTIFICAR UM ÚNICO "

                f"DOCUMENTO GOP NOVO: {ids_novos}"

            )

            return None

        id_documento = ids_novos.pop()

        browser.switch_to.frame(

            browser.find_element(By.ID, "ifrArvore")

        )

        for link in browser.find_elements(By.TAG_NAME, "a"):

            texto = link.text.strip()

            if (

                "CEHAB - DISPONIBILIDADE FINANCEIRA - GOP" in texto.upper()

                and re.search(rf"{id_documento}\)?\s*$", texto)

            ):

                browser.execute_script("arguments[0].click();", link)

                browser.sleep(4)

                browser.switch_to.default_content()

                print(f"ID DO DOCUMENTO NOVO: {id_documento}")

                return id_documento

        browser.switch_to.default_content()

        return None

    except Exception as erro:

        browser.switch_to.default_content()

        print(f"ERRO AO CAPTURAR ID: {erro}")

        return None

def abrir_editar_conteudo(browser):

    try:

        def procurar_botao_em_frames(nivel=0, caminho="raiz", diagnostico=False):

            # O SEI pode renderizar o comando como img, a, button ou input.

            candidatos = browser.find_elements(

                By.XPATH,

                "//*[@title or @alt or self::button or self::a]"

            )

            for elemento in candidatos:

                try:

                    descricao = " ".join([

                        elemento.get_attribute("title") or "",

                        elemento.get_attribute("alt") or "",

                        elemento.text or ""

                    ]).strip().lower()

                    if "editar conteúdo" in descricao or "editar conteudo" in descricao:

                        print(

                            f"BOTÃO EDITAR CONTEÚDO ENCONTRADO EM: "

                            f"{caminho}"

                        )

                        browser.execute_script(

                            "arguments[0].click();",

                            elemento

                        )

                        return True

                except Exception:

                    continue

            if nivel >= 6:

                return False

            frames = browser.find_elements(

                By.TAG_NAME,

                "iframe"

            )

            if diagnostico:

                print(

                    f"IFRAMES EM {caminho}: {len(frames)}"

                )

            for indice in range(len(frames)):

                try:

                    # Recarrega a lista para evitar referência obsoleta.

                    frames_atuais = browser.find_elements(

                        By.TAG_NAME,

                        "iframe"

                    )

                    if indice >= len(frames_atuais):

                        break

                    frame = frames_atuais[indice]

                    frame_id = frame.get_attribute("id") or "sem-id"

                    frame_nome = frame.get_attribute("name") or "sem-name"

                    novo_caminho = (

                        f"{caminho} > iframe[{indice}] "

                        f"id={frame_id} name={frame_nome}"

                    )

                    if diagnostico:

                        print(f"ANALISANDO {novo_caminho}")

                    browser.switch_to.frame(frame)

                    if procurar_botao_em_frames(

                        nivel + 1,

                        novo_caminho,

                        diagnostico

                    ):

                        return True

                    browser.switch_to.parent_frame()

                except Exception as erro_frame:

                    if diagnostico:

                        print(

                            f"NÃO FOI POSSÍVEL ANALISAR "

                            f"{caminho} > iframe[{indice}]: {erro_frame}"

                        )

                    browser.switch_to.default_content()

                    return False

            return False

        limite = time.time() + 30

        tentativa = 0

        while time.time() < limite:

            tentativa += 1

            for janela in browser.window_handles:

                browser.switch_to.window(janela)

                browser.switch_to.default_content()

                diagnostico = tentativa in (1, 5, 10)

                if procurar_botao_em_frames(

                    diagnostico=diagnostico

                ):

                    browser.sleep(5)

                    browser.switch_to.default_content()

                    print("EDITOR DE CONTEÚDO ABERTO")

                    return True

            browser.sleep(1)

        browser.switch_to.default_content()

        print(

            "BOTÃO EDITAR CONTEÚDO NÃO FOI ENCONTRADO "

            "EM NENHUMA JANELA/IFRAME"

        )

        return False

    except Exception as erro:

        browser.switch_to.default_content()

        print(

            f"ERRO AO ABRIR EDITAR CONTEÚDO: {erro}"

        )

        return False

def formatar_valor_monetario(texto):
    """Aceita valores exibidos no padrão brasileiro: 2.227,20 ou R$ 2.227,20."""
    original = str(texto or "").replace("R$", "").replace("\xa0", " ").strip()
    if not original:
        raise ValueError("Valor financeiro vazio")
    try:
        # Os campos da planilha são recebidos com formatação brasileira.
        dec = Decimal(original.replace(".", "").replace(",", "."))
    except InvalidOperation as erro:
        raise ValueError(f"Valor monetário inválido: {original!r}") from erro
    if dec <= 0:
        raise ValueError(f"Valor deve ser positivo: {original}")
    dec = dec.quantize(Decimal("0.01"))
    return f"{dec:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), dec


def preencher_paragrafo_modelo(modelo, dados, solicitacao_numero):
    """Replica o parágrafo financeiro do modelo original para uma linha da planilha."""
    linha = dados["linha_planilha"]
    colunas = dados["linha_completa"]
    if len(colunas) < 15:
        raise ValueError(f"Linha {linha} não possui as colunas de BM/VALOR")

    numero_bm = str(colunas[13]).strip()
    if not numero_bm:
        raise ValueError(f"BM não preenchido na linha {linha}")
    valor, decimal = formatar_valor_monetario(colunas[14])
    valor_extenso = num2words(float(decimal), lang="pt_BR", to="currency")
    fonte = str(dados.get("fonte", "") or "").strip()
    fonte = fonte.zfill(10) if fonte else ""
    ficha = str(dados.get("ficha_financeira", "") or "").strip()
    fonte_descricao = f"{fonte} ({ficha})" if fonte and ficha else (fonte or ficha)
    if not fonte_descricao:
        raise ValueError(f"Fonte/ficha vazia na linha {linha}")

    substituicoes = {
        "XX (),": f"{solicitacao_numero},",
        "BM <b>XX</b>": f"BM <b>{escapar_html(numero_bm)}</b>",
        "R$ X.XXX,XX": f"R$ {valor} ({escapar_html(valor_extenso)})",
        "XXXXXXXXXX": escapar_html(fonte_descricao),
        "(Tipo da Fonte Ex.: Tesouro do Estado)": "",
    }
    resultado = modelo
    for antes, depois in substituicoes.items():
        if antes != "(Tipo da Fonte Ex.: Tesouro do Estado)" and antes not in resultado:
            raise ValueError(f"Modelo financeiro não possui o marcador {antes!r}")
        resultado = resultado.replace(antes, depois, 1)
    return resultado.replace(" .", ".")


def montar_html_consolidado(html_original, linhas, solicitacao_numero, id_documento):
    """Multiplica somente o parágrafo financeiro, preservando o rodapé/assinatura."""
    if not linhas:
        raise ValueError("Não há linhas para consolidar")

    # Localiza o parágrafo que contém os placeholders usados pelo robô anterior.
    paragrafos = re.finditer(r"<p\b[^>]*>.*?</p>", html_original, re.I | re.S)
    modelo = None
    for match in paragrafos:
        trecho = match.group(0)
        if "XX ()," in trecho and "R$ X.XXX,XX" in trecho and "BM <b>XX</b>" in trecho:
            modelo = trecho
            break
    if modelo is None:
        raise ValueError(
            "Parágrafo modelo não encontrado com marcadores XX (),, BM XX e R$ X.XXX,XX. "
            "Verifique o HTML atual do template SEI."
        )

    novos_paragrafos = [
        preencher_paragrafo_modelo(modelo, d, solicitacao_numero) for d in linhas
    ]
    
    # Regra especial para a fonte FINISA 0754006019
    bloco_financeiro = "\n".join(novos_paragrafos)

    fonte_finisa = "0754006019"

    tem_finisa = any(
        fonte_finisa in re.sub(
            r"\D", "",
            str(dados.get("fonte", ""))
        )
        for dados in linhas
    )

    if tem_finisa:
        observacao = (
            "Precisa constar na Nota Fiscal o número do "
            "Contrato de Financiamento FINISA Nº 0655.144-00"
        )

        bloco_financeiro += (
            '\n<p><strong>OBS: '
            + escapar_html(observacao)
            + '</strong></p>'
        )

        print(
            "OBS FINISA FONTE 0754006019: "
            "observação adicionada ao despacho"
        )

    novo_html = html_original.replace(
        modelo,
        bloco_financeiro,
        1
    )

    numero_sei = escapar_html(str(linhas[0]["numero_sei"]).strip())
    if "Processo nº:" in novo_html:
        novo_html = novo_html.replace("Processo nº:", f"Processo nº: {numero_sei}", 1)
    elif "Processo nº" in novo_html:
        novo_html = novo_html.replace("Processo nº", f"Processo nº: {numero_sei}", 1)
    else:
        raise ValueError("Marcador 'Processo nº' não encontrado")
    if "Despacho:" not in novo_html:
        raise ValueError("Marcador 'Despacho:' não encontrado")
    novo_html = novo_html.replace("Despacho:", f"Despacho: {escapar_html(str(id_documento))}", 1)
    novo_html = novo_html.replace("@nome_destinatario@", "GAC")

    partes_resolucao = []
    for dados in linhas:
        resolucao = str(dados.get("resolucao", "") or "").strip()
        if resolucao:
            conteudo = escapar_html(resolucao).replace("\n", "<br>")
            partes_resolucao.append(f"<p><strong>{conteudo}</strong></p>")
    secao_gefin = (
        '<br><hr style="border:1px solid #777;"><br>'
        '<p><strong>À GEFIN,</strong></p>'
        + "\n".join(partes_resolucao) + "<br>"
    )
    if "Atenciosamente," not in novo_html:
        raise ValueError("Rodapé 'Atenciosamente,' não encontrado")
    novo_html = novo_html.replace(
        "Atenciosamente,",
        secao_gefin + '<div style="text-align:center;">Atenciosamente,</div>', 1
    )
    novo_html = re.sub(
        r"([^<>]+?)\s+registrado\(a\)\s+civilmente\s+como\s+[^<]+",
        lambda m: f"<strong>{m.group(1).strip()}</strong>",
        novo_html,
        flags=re.IGNORECASE
    )
    return novo_html


def vincular_cada_referencia(browser, frame, numero_solicitacao, quantidade):
    """Aplica o link interno SEI em cada ocorrência ainda não vinculada."""
    for pos in range(quantidade):
        browser.switch_to.default_content()
        browser.switch_to.frame(frame)
        selecionado = browser.execute_script("""
            var numero = arguments[0];
            var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            var node;
            while ((node = walker.nextNode())) {
                if (node.parentElement && node.parentElement.closest('a')) continue;
                var pos = node.textContent.indexOf(numero);
                if (pos < 0) continue;
                var range = document.createRange();
                range.setStart(node, pos);
                range.setEnd(node, pos + numero.length);
                var sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
                return true;
            }
            return false;
        """, numero_solicitacao)
        if not selecionado:
            raise RuntimeError(f"Referência {pos+1}/{quantidade} não encontrada sem link")
        browser.switch_to.default_content()
        botao_link = browser.find_element(By.XPATH, '//*[@id="cke_119"]/span[1]')
        browser.execute_script("arguments[0].click();", botao_link)
        campo_protocolo = WebDriverWait(browser, 20).until(
            EC.visibility_of_element_located((By.XPATH, "//*[contains(@id,'textInput')]"))
        )
        campo_protocolo.clear()
        campo_protocolo.send_keys(numero_solicitacao)
        ok = WebDriverWait(browser, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//*[contains(@id,'label') and normalize-space()='OK']"))
        )
        browser.execute_script("arguments[0].click();", ok)
        browser.sleep(1)
        print(f"LINK PARA SOLICITAÇÃO {numero_solicitacao}: {pos+1}/{quantidade}")


def editar_mensagem(browser, linhas, documento, id_documento):
    """Preenche um único documento GOP com todas as linhas deste lote."""
    try:
        janelas = browser.window_handles
        browser.switch_to.window(janelas[-1])
        browser.switch_to.default_content()
        browser.sleep(3)
        iframes = browser.find_elements(By.TAG_NAME, "iframe")
        numero_solicitacao = str(documento).strip()

        for indice in range(len(iframes)):
            browser.switch_to.default_content()
            frames_atuais = browser.find_elements(By.TAG_NAME, "iframe")
            if indice >= len(frames_atuais):
                continue
            frame = frames_atuais[indice]
            browser.switch_to.frame(frame)
            html = browser.execute_script("return document.body.innerHTML;")
            if "disponibilidade orçamentária" not in html.lower():
                continue

            # Valida e prepara TODO o conteúdo antes de alterar o editor do SEI.
            novo_html = montar_html_consolidado(html, linhas, numero_solicitacao, id_documento)
            browser.execute_script("document.body.innerHTML = arguments[0];", novo_html)
            browser.find_element(By.TAG_NAME, "body").click()
            browser.sleep(2)
            vincular_cada_referencia(browser, frame, numero_solicitacao, len(linhas))
            browser.switch_to.default_content()
            salvar = WebDriverWait(browser, 20).until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="cke_83_label"]'))
            )
            browser.execute_script("arguments[0].click();", salvar)
            browser.sleep(5)
            browser.close()
            janelas_restantes = browser.window_handles
            if janelas_restantes:
                browser.switch_to.window(janelas_restantes[-1])
                browser.switch_to.default_content()
            return True

        print("EDITOR FINANCEIRO NÃO ENCONTRADO")
        return False
    except UnexpectedAlertPresentException as erro:
        try:
            print("ALERTA SEI:", browser.switch_to.alert.text)
        except Exception:
            pass
        print(f"EDIÇÃO INTERROMPIDA: {erro!r}")
        return False
    except Exception as erro:
        print(f"ERRO EDITAR MENSAGEM: {erro}")
        print("ATENÇÃO: verifique o documento existente no SEI antes de executar novamente")
        return False

def verificar_gop_existente(browser):

    try:

        browser.switch_to.default_content()

        iframes = browser.find_elements(

            "tag name",

            "iframe"

        )

        browser.switch_to.frame(

            iframes[0]

        )

        links = browser.find_elements(

            By.TAG_NAME,

            "a"

        )

        documentos = []

        for link in links:

            texto = link.text.strip()

            if texto:

                documentos.append((texto, link))

        indice_ultima_solicitacao = None

        texto_ultima_solicitacao = None

        for indice, (texto, _link) in enumerate(documentos):

            if (

                "CEHAB - SOLICITAÇÃO DE DISPONIBILIDADE FINANCEIRA"

                in texto.upper()

            ):

                indice_ultima_solicitacao = indice

                texto_ultima_solicitacao = texto

        if indice_ultima_solicitacao is None:

            print("NENHUMA SOLICITAÇÃO ENCONTRADA")

            browser.switch_to.default_content()

            return None

        print(

            f"ÚLTIMA SOLICITAÇÃO: "

            f"{texto_ultima_solicitacao}"

        )

        documentos_depois = documentos[

            indice_ultima_solicitacao + 1:

        ]

        numero_solicitacao = re.search(

            r"(\d{8})",

            texto_ultima_solicitacao

        )

        for texto, link in documentos_depois:

            if (

                "CEHAB - DISPONIBILIDADE FINANCEIRA - GOP"

                in texto.upper()

            ):

                print(

                    f"GOP ENCONTRADA APÓS A ÚLTIMA SOLICITAÇÃO: "

                    f"{texto}"

                )

                numero_documento = re.search(

                    r"(\d{8})$",

                    texto

                )

                if not numero_solicitacao or not numero_documento:

                    browser.switch_to.default_content()

                    return None

                browser.execute_script(

                    "arguments[0].click();",

                    link

                )

                browser.sleep(4)

                browser.switch_to.default_content()

                return {

                    "documento": numero_solicitacao.group(1),

                    "id_documento": numero_documento.group(1)

                }

        print(

            "ÚLTIMA SOLICITAÇÃO AINDA NÃO POSSUI "

            "DOCUMENTO DE DISPONIBILIDADE"

        )

        browser.switch_to.default_content()

        return None

    except Exception as erro:

        browser.switch_to.default_content()

        print(

            f"ERRO VERIFICAR GOP: {erro}"

        )

        return None

def formatar_responsavel(responsavel):

    responsavel = str(responsavel or "").strip()

    if not responsavel:

        return ""

    if responsavel.lower() == "julio.galvao":

        cargo = "Gerente de Orçamento"

    else:

        cargo = "Assessor Administrativo"

    return f"{responsavel} {cargo}"

def voltar_recebidos(browser):

    try:

        # Procura a janela do SEI que contém o botão

        for janela in browser.window_handles:

            browser.switch_to.window(janela)

            browser.switch_to.default_content()

            try:

                botao = WebDriverWait(

                    browser,

                    10

                ).until(

                    EC.element_to_be_clickable(

                        (

                            By.XPATH,

                            '//*[@id="lnkControleProcessos"]'

                        )

                    )

                )

                browser.execute_script(

                    "arguments[0].click();",

                    botao

                )

                browser.sleep(5)

                print("RETORNOU PARA CONTROLE DE PROCESSOS")

                return True

            except Exception:

                continue

        print("BOTÃO CONTROLE DE PROCESSOS NÃO ENCONTRADO")

        return False

    except Exception as erro:

        print(

            f"ERRO AO VOLTAR PARA CONTROLE DE PROCESSOS: {erro}"

        )

        return False

def capturar_link_processo(browser):

    try:

        url = browser.current_url

        parametros = parse_qs(

            urlparse(url).query

        )

        id_procedimento = parametros.get(

            "id_protocolo",

            [None]

        )[0]

        if not id_procedimento:

            return None

        link = (

            "https://sei.pe.gov.br/sei/controlador.php"

            "?acao=procedimento_trabalhar"

            f"&id_procedimento={id_procedimento}"

        )

        return link

    except Exception as erro:

        print(f"ERRO AO CAPTURAR LINK: {erro}")

        return None


if __name__ == "__main__":
    print("Iniciando...")
    print(f"RELATÓRIO ROBÔ DESPACHO ({datetime.now():%d/%m/%Y})")
    while True:
        browser = None
        try:
            lista = obter_aguardando_sei()
            grupos = agrupar_por_sei(lista)
            print("SEIS EM MONITORAMENTO:")
            for sei, linhas in grupos.items():
                print(f"{sei}: linhas {[x['linha_planilha'] for x in linhas]}")
            print(f"TOTAL: {len(lista)} linhas / {len(grupos)} processos SEI")
            if not grupos:
                print("NENHUM AGUARDANDO SEI")
                continue

            browser = iniciar_robo()
            for numero_sei, linhas in grupos.items():
                print("=" * 88)
                print(f"VERIFICANDO {numero_sei}")
                if not verificar_recebidos(browser, numero_sei):
                    continue

                try:
                    solicitacoes = listar_solicitacoes(browser)
                    lotes = preparar_lotes(linhas, solicitacoes, browser)

                    if not lotes:
                        continue
                    # Não criar documento se já existir um GOP no processo;
                    # a posição na árvore SEI não basta para associar com segurança.
                    if existe_gop_no_processo(browser):
                        continue

                    for lote in lotes:
                        linhas_lote = lote["linhas"]
                        solicitacao = lote["solicitacao"]
                        if not conferir_responsavel(linhas_lote):
                            continue
                        print(
                            f"CRIANDO 1 DESPACHO: processo {numero_sei}, "
                            f"solicitação {solicitacao['numero']}, "
                            f"linhas {[d['linha_planilha'] for d in linhas_lote]}"
                        )
                        ids_anteriores = listar_ids_gop(browser)
                        documento = criar_documento(browser, linhas_lote[0], solicitacao)
                        if not documento:
                            print("FALHA AO CRIAR DOCUMENTO")
                            break
                        id_documento = capturar_id_documento(browser, ids_anteriores)
                        if not id_documento:
                            print("DOCUMENTO CRIADO? Não foi possível identificar. Revisão manual.")
                            break
                        if not abrir_editar_conteudo(browser):
                            print(f"NÃO ABRIU EDITOR DO GOP {id_documento}. Revisão manual.")
                            break
                        sucesso = editar_mensagem(browser, linhas_lote, documento, id_documento)
                        if not sucesso:
                            print(f"FALHA AO EDITAR GOP {id_documento}. Revisão manual.")
                            break
                        print(f"GOP {id_documento} SALVO; ATUALIZANDO PLANILHA")
                        # Falha ao atualizar deixa pendência; a trava GOP impede duplicação.
                        atualizar_planilha_enviado([d["linha_planilha"] for d in linhas_lote])
                        print(f"PROCESSO {numero_sei}: lote concluído")
                        if len(lotes) > 1:
                            browser.sleep(2)
                finally:
                    voltar_recebidos(browser)
        except Exception as erro:
            print(f"ERRO GERAL: {erro}")
        finally:
            if browser is not None:
                try:
                    browser.quit()
                except Exception:
                    pass
            time.sleep(30)
