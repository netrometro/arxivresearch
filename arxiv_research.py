import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import google as genai
import streamlit as st
import requests
import time
import datetime

def busca_arxiv(query: str, start_date: str, end_date: str, max_artigos: int = 10):
    url = 'http://export.arxiv.org/api/query'
    MAX_RESULTS_PER_REQUEST = 100
    RATE_LIMIT_SECONDS = 0.35  # Tempo entre as requisições (API do arXiv recomenda no mínimo 0.33s)

    start_fmt = start_date.replace("-", "") + "0000"
    end_fmt = end_date.replace("-", "") + "2359"
    date_filter = f'submittedDate:[{start_fmt} TO {end_fmt}]'
    full_query = f'all:{query} AND {date_filter}'

    artigos = []
    total = -1

    try:
        for start in range(0, max_artigos, MAX_RESULTS_PER_REQUEST):
            results_to_fetch = min(MAX_RESULTS_PER_REQUEST, max_artigos - start)

            params = {
                'search_query': full_query,
                'start': start,
                'max_results': results_to_fetch,
                'sortBy': 'submittedDate',
                'sortOrder': 'descending'
            }

            response = requests.get(url, params=params)
            response.raise_for_status()
            root = ET.fromstring(response.text)

            # Obtém o total apenas na primeira página
            if total == -1:
                total_elem = root.find('{http://a9.com/-/spec/opensearch/1.1/}totalResults')
                total = int(total_elem.text) if total_elem is not None and total_elem.text and total_elem.text.isdigit() else -1
                st.session_state.total = total

            for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                titulo = entry.find('{http://www.w3.org/2005/Atom}title')
                resumo = entry.find('{http://www.w3.org/2005/Atom}summary')
                publicado = entry.find('{http://www.w3.org/2005/Atom}published')
                updated = entry.find('{http://www.w3.org/2005/Atom}updated')
                entry_id = entry.find('{http://www.w3.org/2005/Atom}id')
                primary_category = entry.find('{http://www.w3.org/2005/Atom}primary_category')
                autores = [author.find('{http://www.w3.org/2005/Atom}name').text.strip()
                           for author in entry.findall('{http://www.w3.org/2005/Atom}author')]

                artigo = {
                    'title': titulo.text.strip() if titulo is not None else '',
                    'summary': resumo.text.strip() if resumo is not None else '',
                    'authors': autores,
                    'published': publicado.text if publicado is not None else '',
                    'entry_id': entry_id.text.strip() if entry_id is not None else '',
                    'updated': updated.text if updated is not None else '',
                    'primary_category': primary_category.text.strip() if primary_category is not None else '',
                }
                artigos.append(artigo)

            # Se retornou menos do que o pedido, significa que não há mais artigos
            if len(artigos) >= total or len(artigos) >= max_artigos:
                break

            time.sleep(RATE_LIMIT_SECONDS)  # Respeita limite da API

        return artigos[:max_artigos], None

    except Exception as e:
        return [], f"Erro ao consultar a API do arXiv: {e}"


def getModel(api_key):
    try:
        client = genai.Client(api_key=api_key)
        model = client.chats.create(model="gemini-2.0-flash-lite-001")
        print("Modelo Gemini carregado com sucesso!")
        return model, None
    except Exception as e:
        print(e)
        return None, "Aconteceu algum erro de comunicação com o Gemini!!!"


def classificador(model, titulo, resumo, condicao):
    prompt = (
        f"Você é um assistente acadêmico. Dado o resumo abaixo, diga apenas 'sim' ou 'não' "
        f"se ele trata de: {condicao}\n\n"
        f"Título: {titulo}\n Resumo: {resumo}"
    )
    try:
        response = model.send_message(prompt)
        print(prompt)
        resposta = response.text.strip().lower()
        print(resposta)
        return resposta.startswith("sim")
    except Exception as e:
        st.warning(f"Erro ao processar o artigo '{titulo}': {e}")
        return False


def tradutor(model, texto):
    prompt = (
        f"Você é um tradutor para português do Brasil. Dado o texto abaixo, responda apenas com o texto traduzido.\n "
        f"Texto: {texto}"
    )
    try:
        print(prompt)
        response = model.send_message(prompt)
        if not hasattr(response, "text") or not response.text.strip():
            raise ValueError("Resposta vazia do Gemini.")
        print(response.text)
        return response.text.strip()
    except Exception as e:
        st.warning(f"Erro ao traduzir: '{texto}': {e}")
        return "Erro na tradução"



def gerar_xml(artigos):
    root = ET.Element("papers")
    for i, art in enumerate(artigos, 1):
        item = ET.SubElement(root, "paper", numero=str(i))

        ET.SubElement(item, "title").text = art['title']
        if hasattr(art, "atributo"):
            ET.SubElement(item, "titulo").text = art['titulo']
        

        ET.SubElement(item, "summary").text = art['summary'] or ""

        if hasattr(art, "resumo"):
            ET.SubElement(item, "resumo").text = art['resumo']
        
        ET.SubElement(item, "published").text = str(art['published'])
        ET.SubElement(item, "updated").text = str(art['updated'])
        ET.SubElement(item, "entry_id").text = art['entry_id'] or ""

        ET.SubElement(item, "primary_category").text = art['primary_category'] or ""

        categorias_el = ET.SubElement(item, "categories")
#        for cat in art['primary_categories']:
#            ET.SubElement(categorias_el, "category").text = cat

        autores_el = ET.SubElement(item, "authors")
#        for autor in art['authors']:
#            ET.SubElement(autores_el, "author").text = autor['name']

        links_el = ET.SubElement(item, "links")
#        for link in art['links']:
#            link_el = ET.SubElement(links_el, "id")
#            link_el.set("rel", link.rel or "")
#            link_el.set("href", link.href or "")

    # Conversão com indentação legível
    xml_str = ET.tostring(root, encoding='utf-8')
    pretty_xml = minidom.parseString(xml_str).toprettyxml(indent="  ")

    return pretty_xml.encode('utf-8')





# Configuração da página
st.set_page_config(page_title="ArXiv Research", layout="wide")


def main():
    st.header("ArXiv Research")
    col1, col2, col3 = st.columns(3)

    if 'erro' not in st.session_state:
        st.session_state.erro = ""
    if 'quantidade' not in st.session_state:
        st.session_state.quantidade = 10
    if 'total' not in st.session_state:
        st.session_state.total = 0
    if 'artigos' not in st.session_state:
        st.session_state.artigos = []
    if 'relevantes' not in st.session_state:
        st.session_state.relevantes = []
    if 'traduzidos' not in st.session_state:
        st.session_state.traduzidos = []

    with col1:
        st.subheader("Busca")
        st.markdown("Termos da busca ArXiv. Utilize os operadores lógicos 'and' e 'or' e parênteses para criar buscas complexas.")
        terms = st.text_input("Termos da busca ArXiv")
        st.session_state.quantidade = st.number_input("Digite a quantidade", min_value=1, max_value=2000, value=10)

        start_date = st.date_input("Data de início", value=datetime.date(2020, 1, 1))
        end_date = st.date_input("Data de fim", value=datetime.date.today())

        if st.button("Buscar"):
            if start_date > end_date:
                st.warning("A data de início não pode ser depois da data de fim.")
            else:
                artigos = busca_arxiv(terms, start_date.isoformat(), end_date.isoformat())
                st.markdown(f"Quantidade de artigos no repositório sobre o tema: { st.session_state.total}")
                st.markdown(artigos)

        if st.button("Executar busca"):
            with st.spinner("Consultando ArXiv..."):
                artigos, erro = busca_arxiv(terms, start_date.isoformat(), end_date.isoformat())
                st.markdown(f"Quantidade de artigos no repositório sobre o tema: { st.session_state.total}")
                if erro:
                    st.session_state.erro = erro
                    st.session_state.artigos = ""
                if artigos:
                    st.session_state.erro = ""
                    st.session_state.artigos = artigos

        with st.container():
            if st.session_state.artigos:
                qtd = len(st.session_state.artigos)
                st.markdown(f"**{qtd} artigos encontrados**")

                for i, artigo in enumerate(st.session_state.artigos, 1):
                    st.markdown(f"**{i}. {artigo['published']}**  \n{artigo['title']}")
                    st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
            else:
                st.info("Nenhum artigo carregado.")
        
        
        # Botão para baixar XML
        st.download_button(
            label = "📄 Baixar XML dos Artigos",
            data = gerar_xml(st.session_state.artigos),
            file_name = "artigos_arxiv.xml",
            mime = "application/text"
        )


    with col2:
        st.subheader("Relevância")
        st.markdown("Classificação por relevância de acordo com a condição utilizando o Gemini.")
        st.markdown("A api key não é salva em nenhum lugar. Ela é usada apenas para acessar o Gemini.")
        api_key = st.text_input("Chave Gemini", type="password")
        st.markdown("O Gemini vai encontrar o foco de cada artigo e comparar com a condição de relevância, separando os relevantes de acordo com o tema. Exemplo: 'Nova metodologia'")
        condicao = st.text_input("Condição de relevância")
        st.markdown("**Atenção! O RPM do Gemini gratuito é de 10 requisições por minuto. Leve em consideração que são feitas 3 requisições para cada documento antes de selecionar a quantidade de artigos.**")

        if st.button("Executar classificação"):
            st.session_state.relevantes = []

            model, erro_model = getModel(api_key)
            if erro_model:
                st.session_state.erro = erro_model
                st.error(f"Erro ao criar modelo Gemini: {erro_model}")
            else:
                st.session_state.erro = ""
                st.session_state.relevantes = []
            
            total_artigos = len(st.session_state.artigos)
            quantidade_lidos = 0

            progress_placeholder = st.empty()
            result_placeholder = st.empty()
            msg_placeholder = st.empty()

            if st.session_state.artigos:
                for artigo in st.session_state.artigos:
                    quantidade_lidos += 1

                    if artigo['summary']:
                        is_relevante = classificador(model, artigo['title'], artigo['summary'], condicao)

                        if is_relevante:
                            st.session_state.relevantes.append(artigo)

                    # Atualiza a barra de progresso a cada artigo analisado
                    progress_placeholder.progress(
                        quantidade_lidos / total_artigos,
                        text=f"{quantidade_lidos} de {total_artigos} artigos analisados"
                    )

                    # Atualiza a lista de resultados exibidos
                    results = ""
                    if st.session_state.relevantes:
                        for i, artigo in enumerate(st.session_state.relevantes, 1):
                            results += f"{i}. **{artigo['published']}**\n\n{artigo['title']}\n\n{artigo['summary']}\n\n"
                            results += "<hr style='margin: 10px 0;'>"
                            result_placeholder.markdown(results, unsafe_allow_html=True)
                            msg_placeholder = st.empty()
                    else:
                        msg_placeholder.info("Nenhum artigo relevante encontrado até agora.")

                    time.sleep(60 / 10)

        st.download_button(
            label = "📄 Baixar XML dos Artigos Relevantes",
            data = gerar_xml(st.session_state.relevantes),
            file_name = "relevantes_arxiv.xml",
            mime = "application/text"
        )

    with col3:
        st.subheader("Tradução")
        st.markdown("Tradução de título e resumo dos artigos relevantes.")

        if st.button("Executar tradução"):
            st.session_state.traduzidos = []

            model, erro_model = getModel(api_key)
            if erro_model:
                st.session_state.erro = erro_model
                st.error(f"Erro ao criar modelo Gemini: {erro_model}")
            else:
                st.session_state.erro = ""
                st.session_state.traduzidos = []
            
            total_artigos = len(st.session_state.relevantes)
            quantidade_lidos = 0

            progress_placeholder = st.empty()
            result_placeholder = st.empty()
            msg_placeholder = st.empty()

            if st.session_state.relevantes:
                for artigo in st.session_state.relevantes:
                    quantidade_lidos += 1

                    if artigo['summary'] and artigo['title']:
                        titulo = tradutor(model, artigo['title'])
                        artigo['titulo'] = titulo
                        time.sleep(60 / 10)
                        resumo = tradutor(model, artigo['summary'])
                        artigo['resumo'] = resumo
                        st.session_state.traduzidos.append(artigo)
                        time.sleep(60 / 10)

                    # Atualiza a barra de progresso a cada artigo analisado
                    progress_placeholder.progress(
                        quantidade_lidos / total_artigos,
                        text=f"{quantidade_lidos} de {total_artigos} artigos analisados"
                    )

                    # Atualiza a lista de resultados exibidos
                    results = ""
                    if st.session_state.traduzidos:
                        for i, artigo in enumerate(st.session_state.traduzidos, 1):
                            results += f"{i}. {artigo['published']}  \n{artigo['titulo']}  \n\n**Resumo:** {artigo['resumo']}\n\n({artigo['entry_id']})"
                            results += "<hr style='margin: 10px 0;'>"
                            result_placeholder.markdown(results, unsafe_allow_html=True)
                    else:
                        msg_placeholder.info("Nenhum artigo traduzido até agora.")
        
        # Botão para baixar XML
        st.download_button(
            label="📄 Baixar XML dos Artigos Relevantes Traduzidos",
            data=gerar_xml(st.session_state.traduzidos),
            file_name="traduzidos_arxiv.xml",
            mime="application/text"
        )


if __name__ == "__main__":
    main()
