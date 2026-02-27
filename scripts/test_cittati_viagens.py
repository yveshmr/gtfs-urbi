from datetime import datetime

from app.integrations.cittati.client import CittatiClient
from app.integrations.cittati.viagens import indexar_viagens_por_veiculo_linha_sentido


def main():
    # 👇 HARD CODED
    USER = "yves.ribeiro.urbi"
    PASS = "Rib2023@"

    client = CittatiClient(USER, PASS)

    hoje = datetime.now().strftime("%d/%m/%Y")
    print("Data:", hoje)

    payload = client.consultar_viagens(hoje)

    print("retornoOK:", payload.get("retornoOK"))
    print("qtd viagens:", len(payload.get("viagens") or []))

    idx = indexar_viagens_por_veiculo_linha_sentido(payload)

    c = 0
    for k, v in idx.items():
        print("\nKEY:", k)
        print("inicioProgramado:", v.get("inicioProgramado"))
        print("inicioRealizado:", v.get("inicioRealizado"))
        print("fimProgramado:", v.get("fimProgramado"))
        print("fimRealizado:", v.get("fimRealizado"))
        c += 1
        if c >= 3:
            break


if __name__ == "__main__":
    main()