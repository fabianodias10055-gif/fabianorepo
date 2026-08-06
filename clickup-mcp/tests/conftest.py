import os
import sys
from pathlib import Path

# Os modulos ficam soltos na raiz do projeto, nao num pacote.
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

# Antes de importar clickup_api: o load_dotenv de la nao sobrescreve variaveis
# ja definidas, entao este token falso blinda os testes contra o token real.
os.environ.setdefault("CLICKUP_API_TOKEN", "pk_token_de_teste")

import pytest  # noqa: E402

import clickup_api as api  # noqa: E402


@pytest.fixture(autouse=True)
def cache_limpo():
    api.limpar_cache()
    yield
    api.limpar_cache()
