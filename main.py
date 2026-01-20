import logging
import dotenv

from utils.logging_setup import setup_logging
from db.database.FirebaseConnector import FireStoreConnector
from db.database.Neo4jConnector import Neo4jConnector

# TODO: LIFESPAN CYCLE to setup the enviroment
# TODO: Write the Mocktest for writing the raw documents to Firestore Database
# TODO: Write the full run preprocessing pipelines
# TODO: Create a getway to run the data ingestion pipelines
# TODO: Create getway for frontend to retrives data from database
# TODO: Create the Authentication and Authorization

setup_logging()
logger = logging.getLogger("App Logger")
dotenv.load_dotenv()

def Database_Connecting():
    neo4j_db    = Neo4jConnector()
    firebase_db = FireStoreConnector()
    return neo4j_db, firebase_db

def run():
    neo4j_db, firebase_db = Database_Connecting()


if __name__ == "__main__":
    run()