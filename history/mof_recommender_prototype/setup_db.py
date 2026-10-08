import sqlite3
import pandas as pd

def setup_database():
    """
    Creates a dummy hMOF dataset and saves it to a local SQLite database.
    """
    # Create dummy data with 10 rows representing hMOF dataset
    data = {
        'MOF_ID': [f'hMOF_{str(i).zfill(3)}' for i in range(1, 11)],
        'Surface_Area': [3200.5, 1500.2, 4500.0, 2800.1, 1200.0, 
                         3600.8, 4100.3, 1900.5, 2200.0, 3100.0],
        'Density': [0.85, 1.20, 0.65, 0.95, 1.50, 
                    0.75, 0.70, 1.10, 1.05, 0.88],
        'Pore_Volume': [1.2, 0.5, 1.8, 1.0, 0.4, 
                        1.4, 1.6, 0.7, 0.8, 1.1],
        'Void_Fraction': [0.75, 0.40, 0.85, 0.65, 0.35, 
                          0.80, 0.82, 0.50, 0.55, 0.70]
    }
    
    # Convert dictionary to Pandas DataFrame
    df = pd.DataFrame(data)
    print("Sample Data:")
    print(df.head())
    
    # Connect to SQLite database (will be created if it doesn't exist)
    conn = sqlite3.connect('hmof.db')
    
    # Save the DataFrame to a table named 'materials'
    df.to_sql('materials', conn, if_exists='replace', index=False)
    
    # Close the connection
    conn.close()
    
    print("\nDatabase 'hmof.db' created successfully with table 'materials'.")

if __name__ == "__main__":
    setup_database()
