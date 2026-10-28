"""Diagnóstico somente leitura da coluna FONTE (AE) na planilha BMs 2026.
Execute na pasta do robô, onde existe arquivos_json/arquivo.env e
arquivos_json/credenciais_sheets.json.
"""
import os
import re
import sys
from pathlib import Path

import gspread
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

SEI_ALVO = "0060900036.006015/2026-91"
ABA = "BMs 2026"
COLUNA_FONTE = "AE"
FONTE_FINISA = "0754006019"

BASE_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / "arquivos_json" / "arquivo.env"
CRED_PATH = BASE_DIR / "arquivos_json" / "credenciais_sheets.json"


def normalizar_fonte(valor):
    digitos = re.sub(r"\D", "", str(valor or ""))
    return digitos.zfill(10) if digitos else ""


def main():
    if not ENV_PATH.is_file() or not CRED_PATH.is_file():
        raise FileNotFoundError(
            "Coloque este script na pasta principal do robô, junto à pasta arquivos_json. "
            f"Procurados: {ENV_PATH} e {CRED_PATH}"
        )

    load_dotenv(ENV_PATH)
    planilha_id = os.getenv("PLANILHA_ID")
    if not planilha_id:
        raise ValueError(f"PLANILHA_ID não encontrado em {ENV_PATH}")

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    credenciais = ServiceAccountCredentials.from_json_keyfile_name(str(CRED_PATH), scope)
    planilha = gspread.authorize(credenciais).open_by_key(planilha_id).worksheet(ABA)

    # Mesma rota de leitura usada pelo robô original.
    registros = planilha.get_all_records()
    encontrados = 0
    print(f"Aba: {ABA} | Procurando SEI: {SEI_ALVO}")

    for numero_linha, dados in enumerate(registros, start=2):
        numero_sei = str(dados.get("N° do SEI", "")).strip()
        if numero_sei != SEI_ALVO:
            continue

        encontrados += 1
        fonte_lida = dados.get("FONTE", "")
        fonte_celula = planilha.acell(f"{COLUNA_FONTE}{numero_linha}").value
        fonte_normalizada = normalizar_fonte(fonte_lida)

        print("\n" + "=" * 60)
        print(f"Linha: {numero_linha}")
        print(f"SEI: {numero_sei}")
        print(f"FONTE via get_all_records(): {fonte_lida!r}")
        print(f"Tipo Python: {type(fonte_lida).__name__}")
        print(f"FONTE exibida na célula {COLUNA_FONTE}{numero_linha}: {fonte_celula!r}")
        print(f"FONTE normalizada: {fonte_normalizada!r}")
        print(f"Ativa regra FINISA: {'SIM' if fonte_normalizada == FONTE_FINISA else 'NÃO'}")

    if not encontrados:
        print("\nSEI não encontrado na coluna 'N° do SEI'. Confira o número e o cabeçalho.")
    else:
        print(f"\nTotal de linhas encontradas para o SEI: {encontrados}")
    print("Consulta concluída. Nenhuma célula foi alterada.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERRO: {exc}")
        sys.exit(1)
