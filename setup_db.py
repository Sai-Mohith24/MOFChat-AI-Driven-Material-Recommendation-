import sqlite3
import pandas as pd

def setup_database():
    """
    Reads the real CoRE-MOF dataset from excel and saves it to a local SQLite database.
    """
    dataset_path = '/Users/saimohith/Documents/Sem-5/Data-Driven/tables/coremof.xlsx'
    
    print(f"Loading dataset from {dataset_path}...")
    # Load dataset using openpyxl engine
    df = pd.read_excel(dataset_path, engine='openpyxl')
    
    # Select and rename columns to match the required schema
    # Required schema: MOF_ID, Surface_Area, Density, Pore_Volume, Void_Fraction
    column_mapping = {
        'name': 'MOF_ID',
        'Accessible Surface Area (m^2/g)': 'Surface_Area',
        'Density (cm^3/g)': 'Density',
        'Accessible pore volume (cm^3/g)': 'Pore_Volume',
        'void fraction': 'Void_Fraction'
    }
    
    # Filter only the columns we need and rename them
    df_filtered = df[list(column_mapping.keys())].rename(columns=column_mapping)
    
    # Handle missing or NaN values by filling with 0 or dropping (here we fill with 0 for simplicity)
    df_filtered = df_filtered.fillna(0)
    
    print(f"Dataset loaded. Total rows: {len(df_filtered)}")
    print("Sample Data:")
    print(df_filtered.head())
    
    # Connect to SQLite database (will be created if it doesn't exist)
    conn = sqlite3.connect('hmof.db')
    
    # Save the DataFrame to a table named 'materials'
    df_filtered.to_sql('materials', conn, if_exists='replace', index=False)
    
    # Close the connection
    conn.close()
    
    print("\nDatabase 'hmof.db' created successfully with table 'materials'.")

if __name__ == "__main__":
    setup_database()
