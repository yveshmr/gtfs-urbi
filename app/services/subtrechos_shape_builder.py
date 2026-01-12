from app.core.state import rt
from gtfs_core.pipeline_subtrechos_shape import construir_subtrechos_shape


def build_subtrechos_shape():
    print("⏳ Construindo subtrechos SHAPE...")
    rt.subtrechos_shape = construir_subtrechos_shape()
    print(f"✔ subtrechos SHAPE carregados: {len(rt.subtrechos_shape)}")
