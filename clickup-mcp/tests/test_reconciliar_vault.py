import responses

import clickup_api as api
import reconciliar_vault as rv

B = api.API_BASE

CAIXA_EXEMPLO = """# Caixa de Entrada

## Freelancing / Projeto Jonathan (Arq Viz UE5)

- [ ] [FABIANO] Testar build final | prioridade: high | due: 2026-08-15
- [x] [Ja enviada antes](https://x) - enviada 2026-08-01

## Wingman Marketing / 2. Rotina (Recorrentes)

- [ ] [ANDERSON] [YOUTUBE] Nova rotina
"""


def test_analisar_caixa_extrai_pendentes_com_sufixos():
    itens = rv.analisar_caixa(CAIXA_EXEMPLO)
    assert len(itens) == 2
    assert itens[0]["rotulo"] == "Freelancing / Projeto Jonathan (Arq Viz UE5)"
    assert itens[0]["nome"] == "[FABIANO] Testar build final"
    assert itens[0]["prioridade"] == "high"
    assert itens[0]["due"] == "2026-08-15"
    assert itens[1]["nome"] == "[ANDERSON] [YOUTUBE] Nova rotina"
    assert itens[1]["prioridade"] == "" and itens[1]["due"] == ""


def test_resolver_lista_exato_substring_e_ambiguo():
    mapa = {
        "freelancing / projeto jonathan (arq viz ue5)": "L1",
        "wingman marketing / 2. rotina (recorrentes)": "L2",
        "wingman marketing / 3. tutoriais (backlog de conteúdo)": "L3",
    }
    assert rv.resolver_lista("Freelancing / Projeto Jonathan (Arq Viz UE5)", mapa) == "L1"
    assert rv.resolver_lista("2. Rotina (Recorrentes)", mapa) == "L2"
    # "wingman" casa com duas listas: ambiguidade nao pode chutar
    assert rv.resolver_lista("wingman", mapa) is None
    assert rv.resolver_lista("nao existe", mapa) is None


@responses.activate
def test_empurrar_cria_e_reescreve_linha(tmp_path, monkeypatch):
    (tmp_path / rv.CAIXA).write_text(CAIXA_EXEMPLO, encoding="utf-8")
    monkeypatch.setattr(
        rv, "mapa_de_listas",
        lambda ws: {
            "freelancing / projeto jonathan (arq viz ue5)": "L1",
            "wingman marketing / 2. rotina (recorrentes)": "L2",
        },
    )
    responses.post(f"{B}/list/L1/task", json={"id": "t1", "url": "https://app/t1"})
    responses.post(f"{B}/list/L2/task", json={"id": "t2", "url": "https://app/t2"})

    resultados = rv.empurrar("99", tmp_path)
    assert [r.get("task_id") for r in resultados] == ["t1", "t2"]

    novo = (tmp_path / rv.CAIXA).read_text(encoding="utf-8")
    assert "- [ ]" not in novo  # tudo enviado foi reescrito
    assert "[FABIANO] Testar build final](https://app/t1)" in novo
    # a linha ja enviada antes ficou intacta
    assert "[Ja enviada antes](https://x)" in novo
    # prioridade e due chegaram no corpo da primeira criacao
    import json
    corpo = json.loads(responses.calls[0].request.body)
    assert corpo["priority"] == 2 and corpo["due_date"] > 0


def test_empurrar_sem_caixa_devolve_vazio(tmp_path):
    assert rv.empurrar("99", tmp_path) == []


@responses.activate
def test_puxar_gera_e_remove_orfaos(tmp_path, monkeypatch):
    orfao = tmp_path / "Espelho - Pasta Antiga.md"
    orfao.write_text("velho", encoding="utf-8")
    monkeypatch.setattr(
        rv.ai, "listas_do_workspace",
        lambda ws: [
            ("L1", "Freelancing / Projeto Jonathan"),
            ("L9", "Pasta Vazia / Lista Nova"),
            ("L5", "Get Started"),
        ],
    )
    monkeypatch.setattr(
        rv.ai, "tarefas_do_workspace",
        lambda ws, desde_ms=None: [
            {"id": "1", "name": "[FABIANO] [JONATHAN] T1", "url": "https://app/1",
             "folder": {"name": "Freelancing"}, "list": {"name": "Projeto Jonathan"},
             "status": {"status": "concluído"}},
            {"id": "2", "name": "Solta", "url": "https://app/2",
             "folder": {"name": "hidden"}, "list": {"name": "Get Started"},
             "status": {"status": "pendente"}},
        ],
    )
    notas = rv.puxar("99", tmp_path)
    assert sorted(notas) == [
        "Espelho - Freelancing.md",
        "Espelho - Listas Soltas.md",
        "Espelho - Pasta Vazia.md",  # pasta sem tarefa ganha espelho vazio
    ]
    assert not orfao.exists()
    texto = (tmp_path / "Espelho - Freelancing.md").read_text(encoding="utf-8")
    assert "| [T1](https://app/1) | FABIANO | JONATHAN | concluído |" in texto
