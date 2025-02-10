import pandas as pd

def excel_to_sql_insert(excel_file: str, output_file: str, table_name: str, columns: list[str] = None, start_id: int = 1) -> None:
    # Lê o arquivo Excel
    df = pd.read_excel(excel_file)
    
    # Filtra apenas as colunas desejadas, se especificadas
    if columns:
        df = df[columns]

    # Adiciona o campo `id` sequencial ao DataFrame
    df.insert(0, "id", range(start_id, start_id + len(df)))

    # Gera os comandos INSERT com base nos dados do DataFrame
    with open(output_file, "w") as file:
        for _, row in df.iterrows():
            column_names = ", ".join(df.columns)
            values = ", ".join(
                [f"'{value}'" if isinstance(value, str) else str(value) 
                 for value in row]
            )
            insert_statement = f"INSERT INTO {table_name} ({column_names}) VALUES ({values});"
            file.write(insert_statement + "\n")
    
    print(f"Arquivo '{output_file}' gerado com sucesso!")

# Exemplo de uso:
excel_file = "D:/Projetos/TIQT/tiqt-master/conversao/arquivo.xlsx"
output_file = "D:/Projetos/TIQT/tiqt-master/conversao/arquivo.txt"
table_name = "table"
selected_columns = ["cliente", "cidade","trib"]  # Coloque os nomes reais das colunas desejadas
start_id = 1

excel_to_sql_insert(excel_file, output_file, table_name, selected_columns, start_id)
