import time

import pytest
import responses

import clickup_api as api

B = api.API_BASE


@responses.activate
def test_401_vira_erro_de_token():
    responses.get(f"{B}/team", json={"err": "x"}, status=401)
    with pytest.raises(api.ClickUpError) as e:
        api.get("/team")
    assert "token" in str(e.value)


@responses.activate
def test_403_vira_erro_de_permissao():
    responses.get(f"{B}/team", json={"err": "x"}, status=403)
    with pytest.raises(api.ClickUpError) as e:
        api.get("/team")
    assert "permissao" in str(e.value)


@responses.activate
def test_429_retenta_e_sucede():
    responses.get(
        f"{B}/team", json={}, status=429,
        headers={"X-RateLimit-Reset": str(time.time())},
    )
    responses.get(f"{B}/team", json={"teams": []}, status=200)
    assert api.get("/team") == {"teams": []}


@responses.activate
def test_4xx_comum_nao_retenta():
    responses.get(f"{B}/task/x", json={"err": "no"}, status=404)
    with pytest.raises(api.ClickUpError):
        api.get("/task/x")
    assert len(responses.calls) == 1


@responses.activate
def test_get_paginado_percorre_paginas():
    responses.get(f"{B}/list/1/task", json={"tasks": [{"id": "a"}], "last_page": False})
    responses.get(f"{B}/list/1/task", json={"tasks": [{"id": "b"}], "last_page": True})
    itens = api.get_paginado("/list/1/task")
    assert [i["id"] for i in itens] == ["a", "b"]


@responses.activate
def test_cache_evita_segunda_chamada():
    responses.get(f"{B}/team", json={"teams": [1]})
    assert api.get_cacheado("/team") == {"teams": [1]}
    assert api.get_cacheado("/team") == {"teams": [1]}
    assert len(responses.calls) == 1


@responses.activate
def test_escrita_esvazia_o_cache():
    responses.get(f"{B}/team", json={"teams": [1]})
    responses.post(f"{B}/list/1/task", json={"id": "t"})
    responses.get(f"{B}/team", json={"teams": [2]})
    api.get_cacheado("/team")
    api.post("/list/1/task", json={})
    assert api.get_cacheado("/team") == {"teams": [2]}
    assert len(responses.calls) == 3


def test_rate_limiter_poda_janela_antiga():
    rl = api._RateLimiter(5)
    rl._calls.extend(time.monotonic() - 61 for _ in range(5))
    rl.acquire()  # nao deve bloquear: as entradas antigas saem da janela
    assert len(rl._calls) == 1


def test_em_paralelo_preserva_ordem():
    assert api.em_paralelo(lambda x: x * 2, [1, 2, 3]) == [2, 4, 6]
    assert api.em_paralelo(lambda x: x, []) == []


@responses.activate
def test_upload_multipart(tmp_path):
    arq = tmp_path / "icone.png"
    arq.write_bytes(b"png-fake")
    responses.post(f"{B}/task/abc/attachment", json={"id": "1", "title": "icone.png"})
    r = api.upload_attachment("abc", arq, "icone.png")
    assert r["title"] == "icone.png"
    corpo = responses.calls[0].request.body
    assert b"icone.png" in corpo and b"png-fake" in corpo
