
import os
import time
import warnings
import re
import pandas as pd
import gspread

from datetime import datetime
from google.oauth2.service_account import Credentials

warnings.filterwarnings(
    "ignore",
    message="Workbook contains no default style"
)

PASTA_DOWNLOADS = os.path.join(
    os.path.expanduser("~"),
    "Downloads"
)

print(f"📂 Pasta Downloads: {PASTA_DOWNLOADS}")

if not os.path.isdir(PASTA_DOWNLOADS):
    raise FileNotFoundError(
        f"Pasta Downloads não encontrada: {PASTA_DOWNLOADS}"
    )
ID_PLANILHA_BM = "1lkM9yOjhu_D2nQjRFl-Wt6lNgWPvzl2wbQiaO633-KM"
ABA_BM = "BMs 2026"

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))

ARQUIVO_CREDENCIAIS = os.path.join(
    PASTA_PROJETO,
    "arquivos_json",
    "credenciais.json"
)

class RoboEFisco:

    def __init__(self):

        self.planilha_ob = None
        self.df_ob = None
        self.planilha_le = None
        self.df_le = None
        self.planilha_pd = None
        self.df_pd = None
        self.sei = None
        self.aba_bm = None

    def localizar_extracao_ob(self):

        arquivos_encontrados = []

        for nome_arquivo in os.listdir(PASTA_DOWNLOADS):

            nome = nome_arquivo.lower()

            if not nome.startswith("651101_extracaoob"):
                continue

            if nome.endswith(".crdownload"):
                continue

            caminho = os.path.join(
                PASTA_DOWNLOADS,
                nome_arquivo
            )

            if not os.path.isfile(caminho):
                continue

            arquivos_encontrados.append(caminho)

        if not arquivos_encontrados:

            print("❌ Nenhuma ExtracaoOB encontrada.")
            return False

        self.planilha_ob = max(
            arquivos_encontrados,
            key=os.path.getmtime
        )

        return True

    def ler_excel(self, caminho):

        extensao = os.path.splitext(caminho)[1].lower()

        if extensao == ".xlsx":
            return pd.read_excel(
                caminho,
                engine="openpyxl"
            )

        elif extensao == ".xls":
            return pd.read_excel(
                caminho,
                engine="xlrd"
            )

        else:
            raise ValueError(
                f"Formato não suportado: {extensao}"
            )
        
    def conectar_google_sheets(self):

        try:

            print("📊 Conectando ao Google Sheets...")

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets"
            ]

            credenciais = Credentials.from_service_account_file(
                ARQUIVO_CREDENCIAIS,
                scopes=scopes
            )

            cliente = gspread.authorize(credenciais)

            planilha = cliente.open_by_key(
                ID_PLANILHA_BM
            )

            self.aba_bm = planilha.worksheet(
                ABA_BM
            )

            print(
                f"✅ Planilha conectada: {planilha.title}"
            )

            print(
                f"📑 Aba: {ABA_BM}"
            )

            return True

        except Exception as erro:

            print("❌ Erro ao acessar Google Sheets:")
            print(erro)

            return False

    def obter_seis_monitoramento(self):

        try:

            if self.aba_bm is None:
                return []

            dados = self.aba_bm.get_all_records()

            if not dados:
                return []

            lista = []

            for linha_planilha, registro in enumerate(
                dados,
                start=2
            ):
                status = str(
                    registro.get(
                        "STATUS",
                        ""
                    )
                ).strip().upper()

                if status not in ("ENVIADO", "PAGO"):
                    continue

                numero_sei = str(
                    registro.get(
                        "N° do SEI",
                        ""
                    )
                ).strip()

                if not numero_sei:
                    continue

                numero_bm = str(
                    registro.get("N° do BM", "")
                ).strip()

                inicio = str(
                    registro.get("Início", "")
                ).strip()

                fim = str(
                    registro.get("Fim", "")
                ).strip()

                valor_bm = registro.get(
                    "Valor",
                    ""
                )

                lista.append({
                    "linha_planilha": linha_planilha,
                    "numero_sei": numero_sei,
                    "numero_bm": numero_bm,
                    "inicio": inicio,
                    "fim": fim,
                    "valor_bm": valor_bm
                })

            return lista

        except Exception as erro:

            print(
                f"❌ Erro ao obter SEIs em monitoramento: {erro}"
            )

            return []

    @staticmethod
    def converter_valor(valor):

        if valor is None:
            return None

        texto = str(valor).strip()

        if not texto:
            return None

        texto = (
            texto
            .replace("R$", "")
            .replace(" ", "")
        )

        try:

            if "," in texto:

                texto = (
                    texto
                    .replace(".", "")
                    .replace(",", ".")
                )

                return round(float(texto), 2)

            numero = float(texto)

            if (
                isinstance(valor, (int, float))
                and "." in texto
            ):

                casas_decimais = len(
                    texto.split(".")[1]
                )

                if casas_decimais > 2:
                    numero *= 1000

            return round(numero, 2)

        except (ValueError, TypeError):

            return None

    @staticmethod
    def normalizar_bm(valor):

        texto = str(valor).strip().upper()

        texto = re.sub(
            r"^\s*BM\s*",
            "",
            texto
        )

        texto = re.sub(
            r"^(?:N[º°.]?\s*)?[:\-]?\s*",
            "",
            texto
        )

        resultado = re.search(
            r"0*(\d+)\s*([A-Z]?)",
            texto
        )

        if not resultado:
            return None

        numero = str(int(resultado.group(1)))
        letra = resultado.group(2)

        return numero + letra


    @staticmethod
    def converter_data(data):
        """
        Converte uma data para datetime.date.

        Aceita:
        06/07/2026
        06/07/26
        """

        texto = str(data).strip()

        for formato in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(
                    texto,
                    formato
                ).date()

            except ValueError:
                continue

        return None


    @staticmethod
    def extrair_periodo_observacao(texto):

        texto = str(texto).strip().upper()

        padrao_completo = (
            r"(\d{1,2}/\d{1,2}/\d{2,4})"
            r"\s*(?:A|À|ATÉ)\s*"
            r"(\d{1,2}/\d{1,2}/\d{2,4})"
        )

        resultado = re.search(
            padrao_completo,
            texto
        )

        if resultado:

            inicio = RoboEFisco.converter_data(
                resultado.group(1)
            )

            fim = RoboEFisco.converter_data(
                resultado.group(2)
            )

            if inicio and fim:
                return inicio, fim

        padrao_reduzido = (
            r"\b(\d{1,2})"
            r"\s*(?:A|À|ATÉ)\s*"
            r"(\d{1,2})/(\d{1,2})/(\d{2,4})\b"
        )

        resultado = re.search(
            padrao_reduzido,
            texto
        )

        if resultado:

            dia_inicio = int(resultado.group(1))
            dia_fim = int(resultado.group(2))
            mes = int(resultado.group(3))
            ano = int(resultado.group(4))

            if ano < 100:
                ano += 2000

            try:

                inicio = datetime(
                    ano,
                    mes,
                    dia_inicio
                ).date()

                fim = datetime(
                    ano,
                    mes,
                    dia_fim
                ).date()

                return inicio, fim

            except ValueError:
                return None, None

        return None, None

    @staticmethod
    def validar_observacao(
        texto,
        sei,
        bm,
        inicio,
        fim
    ):

        texto_original = str(texto).strip()
        texto_upper = texto_original.upper()

        sei_procurado = str(sei).strip().upper()

        sei_ok = (
            bool(sei_procurado)
            and sei_procurado in texto_upper
        )

        bm_planilha = RoboEFisco.normalizar_bm(bm)

        resultado_bm = re.search(
            r"\bBM\s*"
            r"(?:N[º°.]?\s*)?"
            r"[:\-]?\s*"
            r"0*(\d+)\s*([A-Z]?)\b",
            texto_upper
        )

        bm_observacao = None

        if resultado_bm:

            numero = str(
                int(resultado_bm.group(1))
            )

            letra = resultado_bm.group(2)

            bm_observacao = numero + letra

        if bm_planilha is None:

            bm_ok = True

        else:

            bm_ok = (
                bm_observacao is not None
                and bm_planilha == bm_observacao
            )

        inicio_planilha = RoboEFisco.converter_data(
            inicio
        )

        fim_planilha = RoboEFisco.converter_data(
            fim
        )

        (
            inicio_observacao,
            fim_observacao
        ) = RoboEFisco.extrair_periodo_observacao(
            texto_original
        )

        periodo_ok = (
            inicio_planilha is not None
            and fim_planilha is not None
            and inicio_observacao is not None
            and fim_observacao is not None
            and inicio_planilha == inicio_observacao
            and fim_planilha == fim_observacao
        )

        print(
            f"   {'✅' if sei_ok else '❌'} SEI: "
            f"{sei_procurado}"
        )

        print(
            f"   {'✅' if bm_ok else '❌'} BM: "
            f"planilha={bm_planilha} | "
            f"OB={bm_observacao}"
        )

        print(
            f"   {'✅' if periodo_ok else '❌'} Período: "
            f"planilha={inicio_planilha} a {fim_planilha} | "
            f"OB={inicio_observacao} a {fim_observacao}"
        )

        return (
            sei_ok
            and bm_ok
            and periodo_ok
        )    

    def carregar_extracao_ob(self):

        if self.planilha_ob is None:
            return False

        try:

            self.df_ob = self.ler_excel(
                self.planilha_ob
            )

            self.df_ob.columns = [
                str(coluna).strip()
                for coluna in self.df_ob.columns
            ]

            return True

        except Exception as erro:

            print("❌ Erro ao carregar ExtracaoOB:")
            print(erro)

            return False

    def procurar_sei_na_ob(self,numero_sei,numero_bm,inicio,fim):

        if self.df_ob is None:
            print("❌ ExtracaoOB não carregada.")
            return []

        coluna_observacao = "Observação"

        if coluna_observacao not in self.df_ob.columns:

            print(
                f"❌ Coluna '{coluna_observacao}' "
                f"não encontrada na ExtracaoOB."
            )

            return []

        print(f"   SEI: {numero_sei}")
        print(f"   BM: {numero_bm}")
        print(f"   Período: {inicio} a {fim}")
        print()

        print(
            f"📄 Verificando "
            f"{os.path.splitext(os.path.basename(self.planilha_ob))[0]}..."
        )

        ocorrencias_validas = []

        for indice, linha in self.df_ob.iterrows():

            observacao = str(
                linha[coluna_observacao]
            ).strip()

            if not observacao:
                continue

            if numero_sei.upper() not in observacao.upper():
                continue

            print(
                f"🔎 SEI encontrado no registro {indice + 2}."
            )

            valido = self.validar_observacao(
                observacao,
                numero_sei,
                numero_bm,
                inicio,
                fim
            )

            if valido:

                ocorrencias_validas.append(linha)

        return ocorrencias_validas

    def validar_valor_ob(self,ocorrencias,valor_bm):

        if not ocorrencias:
            return False

        coluna_valor = "Valor Líquido"

        if coluna_valor not in self.df_ob.columns:

            print(
                f"❌ Coluna '{coluna_valor}' "
                f"não encontrada na ExtracaoOB."
            )

            return False

        total_ob = 0.0

        print()
        print(
            f"💰 Validando valor das OBs "
            f"({len(ocorrencias)} ocorrências):"
        )

        for numero, linha in enumerate(
            ocorrencias,
            start=1
        ):

            valor = self.converter_valor(
                linha[coluna_valor]
            )

            if valor is None:

                print(
                    f"   [{numero}] ❌ Valor não identificado"
                )

                return False

            total_ob += valor

            valor_exibir = (
                f"{valor:,.2f}"
                .replace(",", "X")
                .replace(".", ",")
                .replace("X", ".")
            )

            print(
                f"   [{numero}] R$ {valor_exibir}"
            )

        total_ob = round(total_ob, 2)

        total_ob_exibir = (
            f"{total_ob:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

        valor_planilha = self.converter_valor(
            valor_bm
        )

        if valor_planilha is None:

            print()
            print("💰 Comparação:")
            print(
                f"   [Valor Líquido ExtracaoOB] R$ {total_ob_exibir}"
            )
            print(
                "   [Valor BM 2026]            Não identificado"
            )

            return False


        valor_planilha_exibir = (
            f"{valor_planilha:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

        print()
        print("💰 Comparação:")

        print(
            f"   [Valor Líquido ExtracaoOB] R$ {total_ob_exibir}"
        )

        print(
            f"   [Valor BM 2026]            R$ {valor_planilha_exibir}"
        )


        if valor_planilha <= 0:
            return False

        diferenca = valor_planilha - total_ob

        percentual_desconto = (
            diferenca / valor_planilha
        ) * 100

        print(
            f"   [Desconto]                 "
            f"{percentual_desconto:.2f}%"
        )

        if 0 <= percentual_desconto <= 11:

            print("   ✅ VALORES DENTRO DO LIMITE")
            return True

    def localizar_extracao_le(self):

        arquivos_encontrados = []

        for nome_arquivo in os.listdir(PASTA_DOWNLOADS):

            nome = nome_arquivo.lower()

            if not nome.startswith("651101_extracaole"):
                continue

            if nome.endswith(".crdownload"):
                continue

            caminho = os.path.join(
                PASTA_DOWNLOADS,
                nome_arquivo
            )

            if not os.path.isfile(caminho):
                continue

            arquivos_encontrados.append(caminho)

        if not arquivos_encontrados:

            print("❌ Nenhuma ExtracaoLE encontrada.")
            return False

        self.planilha_le = max(
            arquivos_encontrados,
            key=os.path.getmtime
        )

        return True

    def carregar_extracao_le(self):

        if self.planilha_le is None:
            return False

        try:

            self.df_le = self.ler_excel(
                self.planilha_le
            )

            self.df_le.columns = [
                str(coluna).strip()
                for coluna in self.df_le.columns
            ]

            return True

        except Exception as erro:

            print("❌ Erro ao carregar ExtracaoLE:")
            print(erro)

            return False

    def procurar_sei_na_le(self,numero_sei,numero_bm,inicio,fim):

        if self.df_le is None:
            print("❌ ExtracaoLE não carregada.")
            return None

        coluna_observacao = "Observação da Liquidação"

        if coluna_observacao not in self.df_le.columns:

            print(
                f"❌ Coluna '{coluna_observacao}' "
                f"não encontrada na ExtracaoLE."
            )

            return None

        sei_planilha = str(
            numero_sei
        ).strip().upper()

        bm_planilha = self.normalizar_bm(
            numero_bm
        )

        inicio_planilha = self.converter_data(
            inicio
        )

        fim_planilha = self.converter_data(
            fim
        )

        primeira_ocorrencia = None

        for _, linha in self.df_le.iterrows():

            observacao = str(
                linha[coluna_observacao]
            ).strip()

            if not observacao:
                continue

            texto_upper = observacao.upper()

            if sei_planilha not in texto_upper:
                continue

            sei_ok = True

            resultado_bm = re.search(
                r"\bBM\s*"
                r"(?:N[º°.]?\s*)?"
                r"[:\-]?\s*"
                r"0*(\d+)\s*([A-Z]?)\b",
                texto_upper
            )

            bm_le = None

            if resultado_bm:

                numero = str(
                    int(resultado_bm.group(1))
                )

                letra = resultado_bm.group(2)

                bm_le = numero + letra

            bm_ok = (
                bm_planilha is not None
                and bm_le is not None
                and bm_planilha == bm_le
            )

            inicio_le, fim_le = (
                self.extrair_periodo_observacao(
                    observacao
                )
            )

            periodo_ok = (
                inicio_planilha is not None
                and fim_planilha is not None
                and inicio_le is not None
                and fim_le is not None
                and inicio_planilha == inicio_le
                and fim_planilha == fim_le
            )

            dados_ocorrencia = {
                "linha": linha,
                "sei_ok": sei_ok,
                "bm_ok": bm_ok,
                "periodo_ok": periodo_ok,
                "bm_le": bm_le,
                "inicio_le": inicio_le,
                "fim_le": fim_le
            }

            if primeira_ocorrencia is None:
                primeira_ocorrencia = dados_ocorrencia

            if sei_ok and bm_ok and periodo_ok:

                print(
                    f"   ✅ SEI: {numero_sei}"
                )

                print(
                    f"   ✅ BM: {str(numero_bm).zfill(2)}"
                )

                print(
                    f"   ✅ Período: {inicio} a {fim}"
                )

                return linha

        if primeira_ocorrencia is not None:

            dados = primeira_ocorrencia

            print(
                f"   {'✅' if dados['sei_ok'] else '❌'} "
                f"SEI: {numero_sei}"
            )

            bm_exibir = (
                str(dados["bm_le"]).zfill(2)
                if dados["bm_le"] is not None
                else "Não encontrado"
            )

            print(
                f"   {'✅' if dados['bm_ok'] else '❌'} "
                f"BM: {bm_exibir}"
            )

            inicio_le = dados["inicio_le"]
            fim_le = dados["fim_le"]

            if inicio_le is not None and fim_le is not None:

                periodo_exibir = (
                    f"{inicio_le.strftime('%d/%m/%Y')} "
                    f"a "
                    f"{fim_le.strftime('%d/%m/%Y')}"
                )

            else:

                periodo_exibir = "Não encontrado"

            print(
                f"   {'✅' if dados['periodo_ok'] else '❌'} "
                f"Período: {periodo_exibir}"
            )

        return None

    def escrever_pagamento_planilha(
        self,
        linha_planilha,
        valor
    ):

        if self.aba_bm is None:

            print(
                "❌ Aba do Google Sheets não carregada."
            )

            return False

        try:

            cabecalhos = self.aba_bm.row_values(1)

            coluna_pago = "PAGO"

            if coluna_pago not in cabecalhos:

                print(
                    f"❌ Coluna '{coluna_pago}' não encontrada."
                )

                return False

            numero_coluna_pago = (
                cabecalhos.index(coluna_pago) + 1
            )

            if isinstance(valor, datetime):

                valor_gravar = valor.strftime(
                    "%d/%m/%Y %H:%M:%S"
                )

            else:

                valor_gravar = str(valor).strip()

            self.aba_bm.update_cell(
                linha_planilha,
                numero_coluna_pago,
                valor_gravar
            )

            return True

        except Exception as erro:

            print(
                f"❌ Erro ao atualizar PAGO: {erro}"
            )

            return False

    def escrever_status_planilha(
        self,
        linha_planilha,
        status
    ):

        if self.aba_bm is None:
            print("❌ Aba do Google Sheets não carregada.")
            return False

        try:

            cabecalhos = self.aba_bm.row_values(1)

            coluna_status = "STATUS"

            if coluna_status not in cabecalhos:
                print(
                    f"❌ Coluna '{coluna_status}' não encontrada."
                )
                return False

            numero_coluna_status = (
                cabecalhos.index(coluna_status) + 1
            )

            self.aba_bm.update_cell(
                linha_planilha,
                numero_coluna_status,
                status
            )

            print(
                f'✅ STATUS atualizado para "{status}" '
                f'na linha {linha_planilha}'
            )

            return True

        except Exception as erro:

            print(
                f"❌ Erro ao atualizar STATUS: {erro}"
            )

            return False


    def verificar_pagamento_ob(self, registro_ob):

        coluna_situacao = "Situação"

        if coluna_situacao not in self.df_ob.columns:
            print(f"❌ Coluna '{coluna_situacao}' não encontrada.")
            return None

        situacao = str(
            registro_ob[coluna_situacao]
        ).strip()

        print(f"💰 Situação: {situacao}")

        if situacao.upper() != "PAGA":
            return None

        coluna_data = self.df_ob.columns[12]
        data_pagamento = registro_ob.iloc[12]

        if pd.isna(data_pagamento):
            print("❌ Data de pagamento não encontrada.")
            return None

        print("✅ Coluna 'Data Pagto./Devol.'")

        return data_pagamento

    def verificar_pagamentos_ob(
        self,
        ocorrencias
    ):

        if not ocorrencias:
            return None

        coluna_situacao = "Situação"

        if coluna_situacao not in self.df_ob.columns:

            print(
                f"❌ Coluna '{coluna_situacao}' "
                f"não encontrada."
            )

            return None

        print()
        print("🔎 Verificando situação das OBs...")

        datas_pagamento = []

        for numero, linha in enumerate(
            ocorrencias,
            start=1
        ):

            situacao = str(
                linha[coluna_situacao]
            ).strip()

            print(
                f"   [{numero}] Situação: {situacao}"
            )

            if situacao.upper() != "PAGA":

                print(
                    f"   ❌ Ocorrência {numero} "
                    f"ainda não está PAGA."
                )

                return None

            data_pagamento = linha.iloc[12]

            if pd.isna(data_pagamento):

                print(
                    f"   ❌ Ocorrência {numero} "
                    f"sem Data Pagto./Devol."
                )

                return None

            datas_pagamento.append(
                data_pagamento
            )

        print(
            f"   ✅ {len(ocorrencias)} de "
            f"{len(ocorrencias)} ocorrências PAGAS"
        )

        return max(datas_pagamento)

    def localizar_extracao_pd(self):

        arquivos_encontrados = []

        for nome_arquivo in os.listdir(PASTA_DOWNLOADS):

            nome = nome_arquivo.lower()

            if not nome.startswith("651101_extracaopd"):
                continue

            if nome.endswith(".crdownload"):
                continue

            caminho = os.path.join(
                PASTA_DOWNLOADS,
                nome_arquivo
            )

            if not os.path.isfile(caminho):
                continue

            arquivos_encontrados.append(caminho)

        if not arquivos_encontrados:

            print("❌ Nenhuma ExtracaoPD encontrada.")
            return False

        self.planilha_pd = max(
            arquivos_encontrados,
            key=os.path.getmtime
        )

        return True

    def carregar_extracao_pd(self):

        if self.planilha_pd is None:
            return False

        try:

            self.df_pd = self.ler_excel(
                self.planilha_pd
            )

            self.df_pd.columns = [
                str(coluna).strip()
                for coluna in self.df_pd.columns
            ]

            return True

        except Exception as erro:
            print("❌ Erro ao carregar ExtracaoPD:")
            print(erro)
            return False

    def procurar_pd(self,numero_sei,numero_bm,inicio,fim):

        if self.df_pd is None:
            print("❌ ExtracaoPD não carregada.")
            return None

        coluna_observacao = "Observação"
        coluna_pd = "Previsão de Desembolso"

        if coluna_observacao not in self.df_pd.columns:
            print(
                f"❌ Coluna '{coluna_observacao}' "
                f"não encontrada na ExtracaoPD."
            )
            return None

        if coluna_pd not in self.df_pd.columns:
            print(
                f"❌ Coluna '{coluna_pd}' "
                f"não encontrada na ExtracaoPD."
            )
            return None

        sei_planilha = str(
            numero_sei
        ).strip().upper()

        bm_planilha = self.normalizar_bm(
            numero_bm
        )

        inicio_planilha = self.converter_data(
            inicio
        )

        fim_planilha = self.converter_data(
            fim
        )

        primeira_ocorrencia = None

        for _, linha in self.df_pd.iterrows():

            observacao = str(
                linha[coluna_observacao]
            ).strip()

            if not observacao:
                continue

            texto_upper = observacao.upper()

            if sei_planilha not in texto_upper:
                continue

            sei_ok = True

            resultado_bm = re.search(
                r"\bBM\s*"
                r"(?:N[º°.]?\s*)?"
                r"[:\-]?\s*"
                r"0*(\d+)\s*([A-Z]?)\b",
                texto_upper
            )

            bm_pd = None

            if resultado_bm:

                numero = str(
                    int(resultado_bm.group(1))
                )

                letra = resultado_bm.group(2)

                bm_pd = numero + letra

            bm_ok = (
                bm_planilha is not None
                and bm_pd is not None
                and bm_planilha == bm_pd
            )

            inicio_pd, fim_pd = (
                self.extrair_periodo_observacao(
                    observacao
                )
            )

            periodo_ok = (
                inicio_planilha is not None
                and fim_planilha is not None
                and inicio_pd is not None
                and fim_pd is not None
                and inicio_planilha == inicio_pd
                and fim_planilha == fim_pd
            )

            valor_pd = linha[coluna_pd]

            if pd.isna(valor_pd):
                numero_pd = None
            else:
                numero_pd = str(valor_pd).strip()

                if (
                    not numero_pd
                    or numero_pd.upper() == "NAN"
                ):
                    numero_pd = None

            dados_ocorrencia = {
                "sei_ok": sei_ok,
                "bm_ok": bm_ok,
                "periodo_ok": periodo_ok,
                "bm_pd": bm_pd,
                "inicio_pd": inicio_pd,
                "fim_pd": fim_pd,
                "numero_pd": numero_pd
            }

            if primeira_ocorrencia is None:
                primeira_ocorrencia = dados_ocorrencia

            if (
                sei_ok
                and bm_ok
                and periodo_ok
                and numero_pd is not None
            ):

                print(
                    f"   🔎 PD Encontrada: {numero_pd}"
                )

                print(
                    f"   ✅ SEI: {numero_sei}"
                )

                print(
                    f"   ✅ BM: {str(numero_bm).zfill(2)}"
                )

                print(
                    f"   ✅ Período: {inicio} a {fim}"
                )

                return numero_pd

        if primeira_ocorrencia is not None:

            dados = primeira_ocorrencia

            print(
                "   🔎 PD Encontrada: Não Encontrado"
            )

            print(
                f"   {'✅' if dados['sei_ok'] else '❌'} "
                f"SEI: {numero_sei}"
            )

            bm_exibir = (
                str(dados["bm_pd"]).zfill(2)
                if dados["bm_pd"] is not None
                else "Não encontrado"
            )

            print(
                f"   {'✅' if dados['bm_ok'] else '❌'} "
                f"BM: {bm_exibir}"
            )

            inicio_pd = dados["inicio_pd"]
            fim_pd = dados["fim_pd"]

            if inicio_pd is not None and fim_pd is not None:

                periodo_exibir = (
                    f"{inicio_pd.strftime('%d/%m/%Y')} "
                    f"a "
                    f"{fim_pd.strftime('%d/%m/%Y')}"
                )

            else:

                periodo_exibir = "Não encontrado"

            print(
                f"   {'✅' if dados['periodo_ok'] else '❌'} "
                f"Período: {periodo_exibir}"
            )

            return None

        print(
            "   🔎 PD Encontrada: Não Encontrado"
        )

        print(
            f"   ❌ SEI: {numero_sei}"
        )

        print(
            f"   ❌ BM: {str(numero_bm).zfill(2)}"
        )

        print(
            f"   ❌ Período: {inicio} a {fim}"
        )

        return None

def verificar_sei(robo, dados):

    linha_planilha = dados["linha_planilha"]
    numero_sei = dados["numero_sei"]
    numero_bm = dados["numero_bm"]
    valor_bm = dados["valor_bm"]
    inicio = dados["inicio"]
    fim = dados["fim"]

    robo.sei = numero_sei

    if not robo.localizar_extracao_ob():
        print("=" * 60)
        return

    if not robo.carregar_extracao_ob():
        print("=" * 60)
        return

    ocorrencias_ob = robo.procurar_sei_na_ob(
        numero_sei,
        numero_bm,
        inicio,
        fim
    )

    if ocorrencias_ob:

        print()
        print(
            f"📊 Ocorrências válidas encontradas: "
            f"{len(ocorrencias_ob)}"
        )

        valor_confere = robo.validar_valor_ob(
            ocorrencias_ob,
            valor_bm
        )

        if not valor_confere:

            print()
            print("🛑 Pagamento não identificado")
            print("=" * 60)

            return

        data_pagamento = robo.verificar_pagamentos_ob(
            ocorrencias_ob
        )

        if data_pagamento is None:

            print()
            print("❌ NÃO PAGA")
            print("=" * 60)
            return

        robo.escrever_pagamento_planilha(
            linha_planilha,
            data_pagamento
        )

        robo.escrever_status_planilha(
            linha_planilha,
            "PAGO"
        )

        print("🛑 SEI removido do monitoramento")
        print("=" * 60)

        return

    print("❌ NAO")

    if not robo.localizar_extracao_le():

        print("=" * 60)
        return

    print(
        f"📄 Verificando "
        f"{os.path.basename(robo.planilha_le)}"
    )

    if not robo.carregar_extracao_le():

        print("=" * 60)
        return
    

    print("✅ SIM")

    if not robo.localizar_extracao_pd():

        print("=" * 60)
        return

    print(
        f"📄 Verificando "
        f"{os.path.splitext(os.path.basename(robo.planilha_pd))[0]}"
    )

    if not robo.carregar_extracao_pd():

        print("=" * 60)
        return

    pd_encontrada = robo.procurar_pd(
        numero_sei,
        numero_bm,
        inicio,
        fim
    )

    if pd_encontrada is not None:

        print("✅ SIM")

        status = (
            f"Aguardando Liberação da PD: "
            f"{pd_encontrada}"
        )

        robo.escrever_pagamento_planilha(
            linha_planilha,
            status
        )

        print(
            f"✏️ Aguardando Liberação da PD: "
            f"{pd_encontrada}"
        )

        print("=" * 60)
        return

    print("❌ NAO")

    robo.escrever_pagamento_planilha(
        linha_planilha,
        "Aguardando Liquidação"
    )

    print("✏️ Aguardando Liquidação")
    print("=" * 60)

    return

def main():

    robo = RoboEFisco()

    print("=" * 60)
    print("🤖 VERIFICAÇÃO DO SEI")

    if not robo.conectar_google_sheets():

        print("=" * 60)
        return

    try:

        lista = robo.obter_seis_monitoramento()

        print()
        print(f"TOTAL: {len(lista)} PROCESSOS")
        print("=" * 60)

        if not lista:

            print(
                "⏳ Nenhum processo para verificar."
            )

            return

        PROCESSO_INICIAL = 1527

        lista_processamento = lista[PROCESSO_INICIAL - 1:]

        for numero, dados in enumerate(
            lista_processamento,
            start=PROCESSO_INICIAL
        ):

            print(
                f"📌 PROCESSO "
                f"{numero}/{len(lista_processamento)}"
            )

            print()

            verificar_sei(
                robo,
                dados
            )


        print()
        print("=" * 60)

        print(
            f"🏁 PROCESSAMENTO FINALIZADO - "
            f"{len(lista_processamento)} "
            f"REGISTROS VERIFICADOS"
        )

        print("=" * 60)

        input()

    except KeyboardInterrupt:

        print()
        print("=" * 60)
        print("🛑 PROCESSAMENTO ENCERRADO")
        print("=" * 60)

    except Exception as erro:

        print()
        print(
            f"❌ ERRO NO PROCESSAMENTO: {erro}"
        )


if __name__ == "__main__":
    main()
