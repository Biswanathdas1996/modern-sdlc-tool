"""Database schema API router."""
import re
from fastapi import APIRouter, HTTPException
from repositories import storage
from schemas.requests_database import ConnectDatabaseRequest
from core.logging import log_info, log_error
from utils.exceptions import bad_request, not_found, internal_error
from utils.response import success_response

router = APIRouter(prefix="/database-schema", tags=["database-schema"])


@router.post("/connect")
async def connect_database_schema(request: ConnectDatabaseRequest):
    """
    Connect to a PostgreSQL database and extract schema information.
    
    Args:
        request: Database connection string
        
    Returns:
        Database schema information with tables, columns, and relationships
    """
    try:
        import psycopg2
        
        connection_string = request.connectionString.strip()
        
        if not connection_string:
            raise bad_request("Connection string is required")
        
        # Clean up connection string
        if connection_string.lower().startswith("psql "):
            connection_string = connection_string[5:].strip()
        if (connection_string.startswith("'") and connection_string.endswith("'")) or \
           (connection_string.startswith('"') and connection_string.endswith('"')):
            connection_string = connection_string[1:-1]
        
        projects = storage.get_all_projects()
        if not projects:
            raise bad_request("Please analyze a repository first")
        project = projects[0]
        project_id = project["id"]
        
        try:
            conn = psycopg2.connect(connection_string)
            cursor = conn.cursor()
            
            # Get database name
            cursor.execute("SELECT current_database()")
            result = cursor.fetchone()
            database_name = result[0] if result else "unknown"
            
            # Get schema with relationships
            query = """
                SELECT 
                    t.table_name,
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    c.column_default,
                    CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_primary_key,
                    CASE WHEN fk.column_name IS NOT NULL THEN true ELSE false END as is_foreign_key,
                    fk.foreign_table_name || '.' || fk.foreign_column_name as references_column
                FROM information_schema.tables t
                JOIN information_schema.columns c ON t.table_name = c.table_name AND t.table_schema = c.table_schema
                LEFT JOIN (
                    SELECT ku.table_name, ku.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage ku ON tc.constraint_name = ku.constraint_name
                    WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'
                ) pk ON c.table_name = pk.table_name AND c.column_name = pk.column_name
                LEFT JOIN (
                    SELECT 
                        kcu.table_name,
                        kcu.column_name,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
                ) fk ON c.table_name = fk.table_name AND c.column_name = fk.column_name
                WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
                ORDER BY t.table_name, c.ordinal_position
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            # Organize into tables structure
            tables_map = {}
            for row in rows:
                table_name = row[0]
                if table_name not in tables_map:
                    tables_map[table_name] = []
                tables_map[table_name].append({
                    "name": row[1],
                    "dataType": row[2],
                    "isNullable": row[3] == "YES",
                    "defaultValue": row[4],
                    "isPrimaryKey": row[5],
                    "isForeignKey": row[6],
                    "references": row[7],
                })
            
            # Get row counts for each table
            tables = []
            for table_name, columns in tables_map.items():
                cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                count_result = cursor.fetchone()
                row_count = count_result[0] if count_result else 0
                tables.append({
                    "name": table_name,
                    "columns": columns,
                    "rowCount": row_count,
                })
            
            cursor.close()
            conn.close()
            
            storage.delete_database_schema(project_id)
            
            masked_connection_string = re.sub(
                r"(://[^:]+:)[^@]+(@)",
                r"\1****\2",
                connection_string
            )
            
            schema_info = storage.create_database_schema({
                "projectId": project_id,
                "connectionString": masked_connection_string,
                "databaseName": database_name,
                "tables": tables,
            })
            
            documentation = storage.get_documentation(project_id)
            if documentation:
                storage.update_documentation(project_id, {
                    "databaseSchema": {
                        "databaseName": database_name,
                        "connectionString": masked_connection_string,
                        "tables": tables,
                    },
                })
                log_info(f"Database schema saved to documentation for project {project_id}", "database_schema")
            
            return schema_info
            
        except Exception as db_error:
            log_error("Database connection error", "database_schema", db_error)
            raise bad_request(f"Failed to connect to database: {str(db_error)}")
            
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error processing database schema", "database_schema", e)
        raise internal_error("Failed to process database schema")


@router.get("/current")
async def get_current_database_schema():
    """Get the current database schema."""
    try:
        projects = storage.get_all_projects()
        if not projects:
            return None
        
        schema = storage.get_database_schema(projects[0]["id"])
        return schema
        
    except Exception as e:
        log_error("Error fetching database schema", "database_schema", e)
        raise internal_error("Failed to fetch database schema")


@router.delete("/current")
async def delete_current_database_schema():
    """Delete the current database schema."""
    try:
        projects = storage.get_all_projects()
        if not projects:
            raise not_found("No project found")
        
        project = projects[0]
        project_id = project["id"]
        storage.delete_database_schema(project_id)
        
        documentation = storage.get_documentation(project_id)
        if documentation:
            storage.update_documentation(project_id, {"databaseSchema": None})
            log_info(f"Database schema removed from documentation for project {project_id}", "database_schema")
        
        return success_response(message="Database schema deleted successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error deleting database schema", "database_schema", e)
        raise internal_error("Failed to delete database schema")
