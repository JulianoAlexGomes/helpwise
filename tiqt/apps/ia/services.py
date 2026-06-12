"""
Integração com a IA (Groq) para o assistente de erros.

A escolha do modelo fica em settings.IA_MODELO (lido do .env), então trocar de
modelo — ou até de provedor, reescrevendo só este arquivo — não afeta o resto.
"""
import base64

from django.conf import settings

from .models import BaseConhecimento


class IAError(Exception):
    """Erro amigável para exibir ao usuário quando a IA falha."""


MARCADOR_EMPRESA = "===EMPRESA==="
MARCADOR_EXTERNA = "===EXTERNA==="

SYSTEM_INSTRUCTION = (
    "Você é o assistente de suporte técnico interno da empresa. Um funcionário "
    "(muitas vezes novo) envia o print de um erro e uma breve descrição.\n\n"
    "Priorize SEMPRE as soluções oficiais da empresa (listadas abaixo): elas são a "
    "fonte recomendada e têm prioridade sobre o seu conhecimento geral.\n\n"
    "Identifique o erro na imagem e responda EXATAMENTE neste formato, com os dois "
    "marcadores cada um em sua própria linha:\n\n"
    f"{MARCADOR_EMPRESA}\n"
    "Solução baseada nas soluções oficiais da empresa, em passos numerados, deixando "
    "claro que é a solução recomendada pela empresa. Se NENHUMA solução da base se "
    "aplicar a este erro, escreva somente: Nenhuma solução da base da empresa se "
    "aplica a este erro.\n\n"
    f"{MARCADOR_EXTERNA}\n"
    "Sugestão baseada em conhecimento técnico geral, em passos numerados, deixando "
    "claro que é uma sugestão geral e não um procedimento oficial da empresa.\n\n"
    "Responda em português do Brasil, de forma objetiva. Não invente informações que "
    "não consegue ver na imagem, nem soluções que não existem. Use sempre os dois "
    "marcadores, mesmo que uma das seções seja curta."
)


def buscar_conhecimento(descricao="", departamento=None, limite=15):
    """
    Busca simples (sem embeddings): filtra a base ativa por departamento e
    ranqueia por sobreposição de palavras-chave com a descrição do funcionário.
    """
    qs = BaseConhecimento.objects.filter(ativo=True)
    if departamento is not None:
        qs = qs.filter(_departamento_filter(departamento))

    itens = list(qs)
    if not descricao:
        return itens[:limite]

    termos = {t.strip().lower() for t in descricao.replace(",", " ").split() if len(t) > 2}

    def pontuar(item):
        texto = f"{item.titulo} {item.palavras_chave} {item.descricao_problema}".lower()
        return sum(1 for termo in termos if termo in texto)

    itens.sort(key=pontuar, reverse=True)
    return itens[:limite]


def _departamento_filter(departamento):
    from django.db.models import Q

    # Inclui itens do departamento informado OU sem departamento (gerais)
    return Q(departamento=departamento) | Q(departamento__isnull=True)


def montar_contexto(conhecimentos):
    if not conhecimentos:
        return (
            "Não há soluções oficiais cadastradas na base da empresa para este caso. "
            "Use conhecimento técnico geral e deixe claro que é uma sugestão geral."
        )
    blocos = []
    for c in conhecimentos:
        blocos.append(
            f"- PROBLEMA: {c.titulo}\n"
            f"  SINTOMAS: {c.descricao_problema}\n"
            f"  SOLUÇÃO: {c.solucao}"
        )
    return (
        "SOLUÇÕES OFICIAIS DA EMPRESA (use estas com PRIORIDADE sobre qualquer "
        "conhecimento geral):\n" + "\n".join(blocos)
    )


def separar_secoes(texto):
    """
    Separa a resposta nas duas seções (empresa / externa) a partir dos marcadores.
    Se os marcadores não vierem, joga tudo na seção externa como fallback.
    """
    empresa = None
    externa = None

    if MARCADOR_EMPRESA in texto and MARCADOR_EXTERNA in texto:
        apos_empresa = texto.split(MARCADOR_EMPRESA, 1)[1]
        parte_empresa, parte_externa = apos_empresa.split(MARCADOR_EXTERNA, 1)
        empresa = parte_empresa.strip()
        externa = parte_externa.strip()
    elif MARCADOR_EXTERNA in texto:
        externa = texto.split(MARCADOR_EXTERNA, 1)[1].strip()
    else:
        externa = texto.strip()

    return empresa or "", externa or ""


def transcrever_imagem(imagem_bytes, mime_type):
    """
    Lê a imagem e extrai a mensagem de erro / palavras-chave técnicas, para usar
    na busca da base de conhecimento. Retorna "" se falhar (não quebra o fluxo).
    """
    api_key = getattr(settings, "GROQ_API_KEY", "")
    if not api_key or not imagem_bytes:
        return ""

    try:
        from groq import Groq
    except ImportError:
        return ""

    b64 = base64.b64encode(imagem_bytes).decode("utf-8")
    data_url = f"data:{mime_type or 'image/png'};base64,{b64}"

    try:
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model=settings.IA_MODELO,
            max_tokens=300,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extraia da imagem a mensagem de erro principal e as palavras-chave "
                        "técnicas (códigos, nomes de sistema/programa, termos do erro). "
                        "Responda APENAS com esse texto, sem explicação e sem passos."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Transcreva o erro desta imagem."},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return ""


def analisar_erro(imagem_bytes=None, mime_type=None, descricao="", departamento=None):
    """
    Envia o erro (imagem e/ou descrição) + base de conhecimento para a IA (Groq)
    e retorna o texto com as soluções sugeridas. A imagem é opcional: pode-se
    analisar apenas com a descrição.
    """
    api_key = getattr(settings, "GROQ_API_KEY", "")
    if not api_key:
        raise IAError(
            "A chave da IA (GROQ_API_KEY) não está configurada no .env."
        )

    if not imagem_bytes and not descricao.strip():
        raise IAError("Envie o print do erro ou descreva o problema para analisar.")

    try:
        from groq import Groq
    except ImportError:
        raise IAError(
            "Biblioteca da IA não instalada. Rode: pip install groq"
        )

    # Só transcreve o erro da imagem quando NÃO há descrição (senão usaria uma
    # chamada à toa). Com descrição, ela já serve de base para a busca.
    if imagem_bytes and not descricao.strip():
        texto_busca = transcrever_imagem(imagem_bytes, mime_type)
    else:
        texto_busca = descricao

    conhecimentos = buscar_conhecimento(texto_busca, departamento)
    contexto = montar_contexto(conhecimentos)

    system_text = f"{SYSTEM_INSTRUCTION}\n\n{contexto}"

    if imagem_bytes:
        pergunta = descricao.strip() or "Analise o erro mostrado na imagem e sugira soluções."
        b64 = base64.b64encode(imagem_bytes).decode("utf-8")
        data_url = f"data:{mime_type or 'image/png'};base64,{b64}"
        user_content = [
            {"type": "text", "text": pergunta},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
    else:
        user_content = descricao.strip()

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=settings.IA_MODELO,
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_content},
            ],
        )
    except Exception as exc:  # erros de rede / API
        raise IAError(f"Falha ao consultar a IA: {exc}")

    try:
        texto = (response.choices[0].message.content or "").strip()
    except (AttributeError, IndexError):
        texto = ""

    if not texto:
        raise IAError("A IA não retornou uma resposta. Tente novamente.")

    empresa, externa = separar_secoes(texto)
    return {"empresa": empresa, "externa": externa, "raw": texto}
