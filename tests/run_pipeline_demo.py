# -*- coding: utf-8 -*-

"""
Demonstração do pipeline de criação de SUBTRECHOS,
usando a mesma lógica do código monolítico.

Agora com LOG detalhado.
"""

import requests
import time
from gtfs_core.pipeline_trechos import construir_todos_os_subtrechos


URL_GTFS = "https://servicos.cittati.com.br/GTFS_PLATAFORMA/URBI/GTFS_URBI.zip"


def main():

    print("\n==========================================")
    print("   🚌 PIPELINE DE SUBTRECHOS — DEMO")
    print("==========================================\n")

    # -------------------------------
    # Download GTFS
    # -------------------------------
    print("🔄 Baixando GTFS estático...")
    t0 = time.time()

    resp = requests.get(URL_GTFS)
    resp.raise_for_status()

    t1 = time.time()
    print(f"✅ Download concluído em {t1 - t0:.1f} segundos\n")

    # -------------------------------
    # Executa pipeline
    # -------------------------------
    print("🚧 Executando pipeline de subtrechos...")
    t2 = time.time()

    subtrechos = construir_todos_os_subtrechos(resp.content)

    t3 = time.time()

    print("\n==========================================")
    print("              RESULTADO")
    print("==========================================")
    print(f"⏱ Tempo total pipeline: {t3 - t2:.1f} segundos")
    print(f"🚍 Subtrechos gerados:  {len(subtrechos)}")
    print("==========================================\n")

    # -------------------------------
    # Mostra primeiros exemplos
    # -------------------------------
    print("📌 Primeiros 10 subtrechos:\n")

    for s in subtrechos[:10]:
        print(f"- {s.s1}  →  {s.s2} | {s.distance_m:.1f} m | grupo={s.group}")

    print("\n🏁 Finalizado.\n")


if __name__ == "__main__":
    main()
