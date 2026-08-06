import responses

import anexar_icones as ai
import clickup_api as api

B = api.API_BASE


def test_categoria_conhecida():
    assert ai.categoria_de("[ANDERSON] [YOUTUBE] Gravar video") == "YOUTUBE"


def test_categoria_com_digito():
    assert ai.categoria_de("[FABIANO] [N8N] Avaliar automacao") == "N8N"


def test_categoria_de_banner():
    assert ai.categoria_de("[ANDERSON] [TUTORIAL] 01 Setup") == "TUTORIAL"
    assert "TUTORIAL" in ai.CATEGORIAS_COM_BANNER


def test_sem_categoria():
    assert ai.categoria_de("[TEMP] rascunho") is None
    assert ai.categoria_de("Tarefa 1") is None


def test_estado_do_anexo_detecta_divergencia():
    # Caso real: patreon.png coral (1802 B) com o mesmo nome do correto (1759 B).
    anexos = [{"title": "patreon.png", "size": 1802}]
    assert ai.estado_do_anexo(anexos, "patreon.png", 1759) == "divergente"
    assert ai.estado_do_anexo(anexos, "patreon.png", 1802) == "ok"
    assert ai.estado_do_anexo(anexos, "youtube.png", 100) == "ausente"
    assert ai.estado_do_anexo([], "x.png", None) == "ausente"


@responses.activate
def test_anexos_da_tarefa_sem_o_campo():
    # Regressao: ha endpoints que nao devolvem a chave attachments.
    responses.get(f"{B}/task/t1", json={"id": "t1", "name": "x"})
    assert ai.anexos_da_tarefa("t1") == []


@responses.activate
def test_tarefas_do_workspace_paginado_e_incremental():
    responses.get(f"{B}/team/99/task", json={"tasks": [{"id": "a"}]})
    responses.get(f"{B}/team/99/task", json={"tasks": []})
    ts = ai.tarefas_do_workspace("99", desde_ms=123)
    assert [t["id"] for t in ts] == ["a"]
    assert "date_updated_gt=123" in responses.calls[0].request.url


def test_rotulo_da_lista():
    t = {"folder": {"name": "Wingman Marketing"}, "list": {"name": "1. Setup"}}
    assert ai.rotulo_da_lista(t) == "Wingman Marketing / 1. Setup"
    solta = {"folder": {"name": "hidden"}, "list": {"name": "Solta"}}
    assert ai.rotulo_da_lista(solta) == "Solta"


def test_cursor_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "CURSOR_PATH", tmp_path / "cursor.json")
    assert ai._ler_cursor("99") is None
    ai._salvar_cursor("99", 1234)
    assert ai._ler_cursor("99") == 1234
    ai._salvar_cursor("outro", 5678)
    assert ai._ler_cursor("99") == 1234
