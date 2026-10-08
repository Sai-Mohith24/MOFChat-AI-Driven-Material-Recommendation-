"""
02_data_preprocessing.py

This script handles the initial data preprocessing of the raw dataset.
It follows the specified steps:
1. Load dataset
2. Remove duplicates
3. Handle missing values
4. Fix data types
"""

import pandas as pd
import numpy as np
import os

def preprocess_data(input_path: str, output_path: str):
    print(f"--- 1. Loading dataset ---")
    print(f"Reading from {input_path}...")
    # Using read_excel since the source is .xlsx
    df = pd.read_excel(input_path, engine='openpyxl')
    print(f"Initial Shape: {df.shape}")
    
    print("\n--- 2. Removing duplicates ---")
    initial_rows = len(df)
    df = df.drop_duplicates()
    print(f"Dropped {initial_rows - len(df)} duplicate rows. New Shape: {df.shape}")
    
    print("\n--- 3. Handling missing values ---")
    # We will drop incomplete rows for categorical/metadata and fill numeric with mean
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    
    # Fill numeric columns with their mean
    df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].mean())
    
    # Drop rows that still have missing values (e.g. string/categorical columns)
    df = df.dropna()
    print(f"Shape after handling missing values: {df.shape}")
    
    print("\n--- 4. Fixing data types ---")
    # Convert obvious numeric columns stored as objects to numeric (ignoring errors to keep text as text)
    for col in df.columns:
        if df[col].dtype == 'object':
            try:
                # Try converting to numeric first
                df[col] = pd.to_numeric(df[col])
            except (ValueError, TypeError):
                try:
                    # If it's a date string, try converting to datetime
                    df[col] = pd.to_datetime(df[col])
                except (ValueError, TypeError):
                    pass
    
    print("Data types after fixing:")
    print(df.dtypes)
    
    # Save the cleaned dataset
    print(f"\n--- Saving Processed Dataset ---")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Cleaned dataset saved to {output_path}")
    
    return df

if __name__ == "__main__":
    input_file = '../../data/coremof.xlsx'
    output_file = '../../data/coremof_cleaned.csv'
    
    if os.path.exists(input_file):
        preprocess_data(input_file, output_file)
    else:
        print(f"File not found: {input_file}")
