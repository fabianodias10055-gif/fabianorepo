import json

import pytest
import responses

import clickup_api as api
import server

B = api.API_BASE


@pytest.fixture(autouse=True)
def audit_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "AUDIT_LOG", tmp_path / "alteracoes.jsonl")


@responses.activate
def test_listar_statuses():
    responses.get(f"{B}/list/1", json={"statuses": [
        {"status": "pendente", "type": "open"},
        {"status": "concluído", "type": "closed"},
    ]})
    saida = json.loads(server.listar_statuses("1"))
    assert saida == [
        {"status": "pendente", "tipo": "open"},
        {"status": "concluído", "tipo": "closed"},
    ]


@responses.activate
def test_concluir_tarefa_descobre_status_final():
    responses.get(f"{B}/task/t1", json={"id": "t1", "list": {"id": "L1"}})
    responses.get(f"{B}/list/L1", json={"statuses": [
        {"status": "pendente", "type": "open"},
        {"status": "concluído", "type": "closed"},
    ]})
    responses.put(f"{B}/task/t1", json={"id": "t1", "name": "X",
                                        "status": {"status": "concluído"}})
    saida = json.loads(server.concluir_tarefa("t1"))
    assert saida["status"] == "concluído"
    corpo = json.loads(responses.calls[-1].request.body)
    assert corpo == {"status": "concluído"}


@responses.activate
def test_concluir_tarefa_sem_status_final():
    responses.get(f"{B}/task/t1", json={"id": "t1", "list": {"id": "L1"}})
    responses.get(f"{B}/list/L1", json={"statuses": [
        {"status": "pendente", "type": "open"},
    ]})
    saida = json.loads(server.concluir_tarefa("t1"))
    assert "erro" in saida and saida["statuses"] == ["pendente"]


@responses.activate
def test_marcar_item_checklist():
    responses.put(f"{B}/checklist/c1/checklist_item/i1", json={})
    saida = json.loads(server.marcar_item_checklist("c1", "i1", True))
    assert saida["ok"] is True
    corpo = json.loads(responses.calls[0].request.body)
    assert corpo == {"resolved": True}


@responses.activate
def test_criar_tarefas_em_lote_reporta_erro_por_posicao():
    responses.post(f"{B}/list/1/task", json={"id": "a", "name": "Boa"})
    saida = json.loads(server.criar_tarefas_em_lote("1", [
        {"nome": "Boa"},
        {"nome": "Ruim", "prioridade": "urgentissima"},
        {"descricao": "sem nome"},
    ]))
    assert len(saida["criadas"]) == 1
    assert [e["posicao"] for e in saida["erros"]] == [1, 2]


@responses.activate
def test_duplicar_tarefa_copia_sem_datas():
    responses.get(f"{B}/task/t1", json={
        "id": "t1", "name": "Modelo", "description": "passos",
        "list": {"id": "L1"}, "priority": {"priority": "high"},
        "tags": [{"name": "mkt"}], "due_date": "1754500000000",
        "checklists": [{"id": "c1", "name": "Pipeline",
                        "items": [{"id": "i1", "name": "gravar"}]}],
    })
    responses.post(f"{B}/list/L1/task", json={"id": "t2", "name": "Modelo (copia)"})
    responses.post(f"{B}/task/t2/checklist", json={"checklist": {"id": "c2"}})
    responses.post(f"{B}/checklist/c2/checklist_item", json={})
    saida = json.loads(server.duplicar_tarefa("t1"))
    assert saida["id"] == "t2"
    corpo = json.loads(responses.calls[1].request.body)
    assert corpo["name"] == "Modelo (copia)"
    assert corpo["priority"] == 2
    assert corpo["tags"] == ["mkt"]
    assert "due_date" not in corpo and "status" not in corpo
    item = json.loads(responses.calls[3].request.body)
    assert item == {"name": "gravar"}


@responses.activate
def test_responder_comentario():
    responses.post(f"{B}/comment/c9/reply", json={"id": "r1"})
    saida = json.loads(server.responder_comentario("c9", "combinado"))
    assert saida["reply_id"] == "r1"


@responses.activate
def test_registrar_tempo_monta_corpo():
    responses.post(f"{B}/team/9/time_entries", json={"data": {"id": "e1"}})
    saida = json.loads(server.registrar_tempo("9", "t1", 30, "edicao"))
    assert saida["entry_id"] == "e1"
    corpo = json.loads(responses.calls[0].request.body)
    assert corpo["tid"] == "t1"
    assert corpo["duration"] == 30 * 60_000
    assert corpo["start"] > 0


def test_registrar_tempo_recusa_zero():
    saida = json.loads(server.registrar_tempo("9", "t1", 0))
    assert "erro" in saida


@responses.activate
def test_criar_meta_com_key_result():
    responses.post(f"{B}/team/9/goal", json={"goal": {"id": "g1"}})
    responses.post(f"{B}/goal/g1/key_result", json={"key_result": {"id": "k1"}})
    saida = json.loads(server.criar_meta("9", "20 tutoriais", alvo=20, unidade="tutoriais"))
    assert saida == {"goal_id": "g1", "key_result_id": "k1"}
    kr = json.loads(responses.calls[1].request.body)
    assert kr["steps_end"] == 20 and kr["type"] == "number"


def test_ler_audit_log_filtra_por_acao(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    audit = tmp_path / "audit.jsonl"
    agora = datetime.now(timezone.utc).isoformat()
    linhas = [
        {"quando": agora, "acao": "criar_tarefa", "task_id": "a"},
        {"quando": agora, "acao": "editar_tarefa", "task_id": "b",
         "snapshot": {"grande": "sim"}},
    ]
    audit.write_text(
        "\n".join(json.dumps(l) for l in linhas) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(server, "AUDIT_LOG", audit)

    tudo = json.loads(server.ler_audit_log(dias=1))
    assert len(tudo) == 2
    assert tudo[0]["acao"] == "editar_tarefa"  # mais recente primeiro
    assert tudo[0]["snapshot"] == "(guardado)"

    so_criar = json.loads(server.ler_audit_log(dias=1, acao="criar_tarefa"))
    assert [r["task_id"] for r in so_criar] == ["a"]


@responses.activate
def test_exportar_board_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "EXPORT_DIR", tmp_path / "exports")
    responses.get(f"{B}/team/9/task", json={"tasks": [{
        "id": "1", "name": "Tarefa Á", "status": {"status": "pendente"},
        "folder": {"name": "WM"}, "list": {"name": "Setup"},
        "assignees": [{"username": "Fabiano"}],
    }]})
    responses.get(f"{B}/team/9/task", json={"tasks": []})
    saida = json.loads(server.exportar_board("9", formato="csv"))
    assert saida["tarefas"] == 1
    arquivo = server.EXPORT_DIR / saida["arquivo"].split("\\")[-1]
    texto = arquivo.read_text(encoding="utf-8-sig")
    assert "Tarefa Á" in texto and "WM / Setup" in texto


def test_criar_lista_exige_um_destino():
    saida = json.loads(server.criar_lista("Nova"))
    assert "erro" in saida
    saida = json.loads(server.criar_lista("Nova", folder_id="f", space_id="s"))
    assert "erro" in saida


def test_novas_escritas_respeitam_dry_run(monkeypatch):
    monkeypatch.setattr(server, "SIMULAR", True)
    with responses.RequestsMock():  # nenhuma rota: chamada real falharia
        for chamada in (
            lambda: server.criar_lista("N", folder_id="f"),
            lambda: server.criar_pasta("s", "N"),
            lambda: server.duplicar_tarefa("t1"),
            lambda: server.concluir_tarefa("t1"),
            lambda: server.mudar_status_em_lote(["t1"], "pendente"),
            lambda: server.marcar_item_checklist("c", "i"),
            lambda: server.convidar_membro("9", "a@b.c"),
            lambda: server.registrar_tempo("9", "t1", 5),
            lambda: server.criar_meta("9", "Meta"),
        ):
            assert json.loads(chamada())["simulado"] is True
