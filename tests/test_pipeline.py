from gtfs_core.trechos import carregar_trechos_dos_pairs
from gtfs_core.pairs import PAIRS


def main():
    print("Carregando trechos a partir dos pairs...\n")

    trechos = carregar_trechos_dos_pairs(
        pairs=PAIRS,
        shape_id="(a definir depois por GTFS)"
    )

    print(f"TOTAL DE TRECHOS: {len(trechos)}\n")

    print("Primeiros 10:\n")
    for t in trechos[:10]:
        print({
            "origem": t.stop_id_origem,
            "destino": t.stop_id_destino,
            "shape": t.shape_id
        })

    print("\nOK 👍")


if __name__ == "__main__":
    main()
