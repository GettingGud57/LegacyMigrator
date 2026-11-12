from diff import load, reconcile, print_verdict



if __name__ == "__main__":
    staging = "Integration.ETL Cutoff.parquet"
    before = load(f"snapshots/city/before/{staging}")
    for col in before[0]:
        print(f"  {col}: {type(before[0][col])}")



"""
  City Staging Key: <class 'int'>
  WWI City ID: <class 'int'>
  City: <class 'str'>
  State Province: <class 'str'>
  Country: <class 'str'>
  Continent: <class 'str'>
  Sales Territory: <class 'str'>
  Region: <class 'str'>
  Subregion: <class 'str'>
  Location: <class 'str'>
  Latest Recorded Population: <class 'int'>
  Valid From: <class 'datetime.datetime'>
  Valid To: <class 'datetime.datetime'>  



  Lineage Key: <class 'int'>
  Data Load Started: <class 'datetime.datetime'>
  Table Name: <class 'str'>
  Data Load Completed: <class 'datetime.datetime'>
  Was Successful: <class 'bool'>
  Source System Cutoff Time: <class 'datetime.datetime'>


  Table Name: <class 'str'>
  Cutoff Time: <class 'datetime.datetime'>

"""

