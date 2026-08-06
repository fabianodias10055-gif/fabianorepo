import json

import pytest
import responses

import clickup_api as api
import server

B = api.API_BASE


@pytest.fixture(autouse=True)
def audit_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "AUDIT_LOG", tmp_path / "alteracoes.jsonl")


def test_para_ms_formatos():
    assert server._para_ms("2026-08-06") > 0
    assert server._para_ms("2026-08-06 14:30") > server._para_ms("2026-08-06")
    with pytest.raises(ValueError):
        server._para_ms("06/08/2026")


def test_dry_run_global_nao_chama_a_api(monkeypatch):
    monkeypatch.setattr(server, "SIMULAR", True)
    with responses.RequestsMock():  # nenhuma rota registrada: chamada real falharia
        saida = json.loads(server.criar_tarefa("1", "Teste"))
        assert saida["simulado"] is True and saida["acao"] == "criar_tarefa"
        saida = json.loads(server.apagar_webhook("w1"))
        assert saida["simulado"] is True


@responses.activate
def test_criar_tarefa_com_datas_parent_e_tags():
    responses.post(f"{B}/list/1/task", json={"id": "t", "name": "X"})
    server.criar_tarefa(
        "1", "X", due_date="2026-08-10", parent="pai", tags=["mkt"], responsaveis=[7]
    )
    corpo = json.loads(responses.calls[0].request.body)
    assert corpo["parent"] == "pai"
    assert corpo["tags"] == ["mkt"]
    assert corpo["assignees"] == [7]
    assert corpo["due_date"] > 0


def test_criar_tarefa_data_invalida_nao_chama_api():
    with responses.RequestsMock():
        saida = json.loads(server.criar_tarefa("1", "X", due_date="10/08/2026"))
    assert "erro" in saida


@responses.activate
def test_editar_tarefa_grava_snapshot(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setattr(server, "AUDIT_LOG", audit)
    responses.get(f"{B}/task/t1", json={
        "id": "t1", "name": "Antes", "list": {"id": "L1"},
        "status": {"status": "pendente"},
    })
    responses.put(f"{B}/task/t1", json={"id": "t1", "name": "Depois"})
    server.editar_tarefa("t1", nome="Depois")
    registro = json.loads(audit.read_text(encoding="utf-8").splitlines()[-1])
    assert registro["snapshot"]["nome"] == "Antes"
    assert registro["snapshot"]["list_id"] == "L1"


@responses.activate
def test_relatorio_board_agrega():
    tarefas = [
        {"id": "1", "name": "[FABIANO] [RESEND] a",
         "status": {"status": "pendente", "type": "open"},
         "folder": {"name": "WM"}, "list": {"name": "Setup"}, "date_updated": "1"},
        {"id": "2", "name": "[ANDERSON] [YOUTUBE] b",
         "status": {"status": "concluído", "type": "closed"},
         "folder": {"name": "WM"}, "list": {"name": "Rotina"}, "date_updated": "1"},
    ]
    responses.get(f"{B}/team/9/task", json={"tasks": tarefas})
    responses.get(f"{B}/team/9/task", json={"tasks": []})
    r = json.loads(server.relatorio_board("9"))
    assert r["total"] == 2
    assert r["por_dono"] == {"FABIANO": 1, "ANDERSON": 1}
    assert r["por_categoria"] == {"RESEND": 1, "YOUTUBE": 1}
    assert r["por_lista"] == {"WM / Setup": 1, "WM / Rotina": 1}
    # So a tarefa aberta conta como parada; a concluida nao.
    assert [p["id"] for p in r["paradas"]] == ["1"]


@responses.activate
def test_anexar_url_respeita_o_teto(monkeypatch):
    monkeypatch.setattr(server, "MAX_DOWNLOAD_BYTES", 10)
    responses.get("https://exemplo.com/grande.png", body=b"x" * 20)
    saida = json.loads(server.anexar_url("t1", "https://exemplo.com/grande.png"))
    assert "teto" in saida["erro"]


@responses.activate
def test_restaurar_tarefa_a_partir_do_snapshot(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    snap = {
        "task_id": "morta", "list_id": "L1", "nome": "Recuperada",
        "descricao": "d", "status": "pendente", "prioridade": "high",
        "responsaveis": [7], "tags": ["mkt"], "due_date": None,
        "start_date": None, "parent": None,
    }
    audit.write_text(
        json.dumps({"acao": "apagar_tarefa", "snapshot": snap}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "AUDIT_LOG", audit)
    responses.post(f"{B}/list/L1/task", json={"id": "nova", "name": "Recuperada"})
    saida = json.loads(server.restaurar_tarefa("morta"))
    assert saida["id"] == "nova"
    corpo = json.loads(responses.calls[0].request.body)
    assert corpo["priority"] == 2
    assert corpo["assignees"] == [7]
    assert corpo["tags"] == ["mkt"]


def test_restaurar_sem_snapshot(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    audit.write_text("", encoding="utf-8")
    monkeypatch.setattr(server, "AUDIT_LOG", audit)
    saida = json.loads(server.restaurar_tarefa("nunca-existiu"))
    assert "erro" in saida


def test_resend_desativado_sem_chave(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    saida = json.loads(server.enviar_email_resend("a", "<b>x</b>"))
    assert "RESEND_API_KEY" in saida["erro"]


def test_discord_desativado_sem_url(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    saida = json.loads(server.notificar_discord("oi"))
    assert "DISCORD_WEBHOOK_URL" in saida["erro"]


def test_apagar_tarefa_bloqueada_por_padrao(monkeypatch):
    monkeypatch.setattr(server, "PERMITIR_APAGAR", False)
    saida = json.loads(server.apagar_tarefa("t1"))
    assert saida["erro"] == "exclusao desabilitada"
