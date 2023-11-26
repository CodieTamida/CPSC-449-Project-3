from botocore.exceptions import ClientError
import logging
from decimal import Decimal
import json
from pprint import pprint

logger = logging.getLogger(__name__)

class DynamodbData:
    def __init__(self, dynamodb_resource):
        
        self.dynamodb_resource = dynamodb_resource

    def get_sample_data(self, file_name):
        try:
            with open(file_name) as file:
                data = json.load(file, parse_float=Decimal)
        except FileNotFoundError:
            print(
                f"File {file} not found"
            )
            raise
        else:
            # The sample file lists over 4000 movies, return only the first 250.
            return data
    
    def write_batch(self, data, table):

        try:
            with table.batch_writer() as writer:
                for d in data:
                    writer.put_item(Item=d)
        except ClientError as err:
            logger.error(
                "Couldn't load data into table %s. Here's why: %s: %s",
                table.name,
                err.response["Error"]["Code"],
                err.response["Error"]["Message"],
            )
            raise
    
    def run_partiql(self, statements, param_list):
        try:
            output = self.dynamodb_resource.meta.client.batch_execute_statement(
                Statements=[
                    {"Statement": statement, "Parameters": params}
                    for statement, params in zip(statements, param_list)
                ]
            )
        except ClientError as err:
            if err.response["Error"]["Code"] == "ResourceNotFoundException":
                logger.error(
                    "Couldn't execute batch of PartiQL statements because the table "
                    "does not exist."
                )
            else:
                logger.error(
                    "Couldn't execute batch of PartiQL statements. Here's why: %s: %s",
                    err.response["Error"]["Code"],
                    err.response["Error"]["Message"],
                )
            raise
        else:
            return output

        
    def read_data(self, table_name, table_key, data):
    
        statements = [f'SELECT * FROM "{table_name}" WHERE {table_key}=?'] * len(data)
        params = [[d[table_key]] for d in data]
        print(params)
        output = self.run_partiql(statements, params)
        for item in output["Responses"]:
            pprint(item["Item"])
        print("-" * 88)

    def load_dummy_data(self, table_name, file_name):
        
        print(f"\nReading data from '{file_name}' to insert into your table '{table_name}'")
        data = self.get_sample_data(file_name)
        self.write_batch(data, table_name)
        print(f"\nWrote {len(data)} objects into {table_name}.")

        # Check if dummy data is loaded successfully in the tables

        '''
        if file_name == 'jsonData/users.json':   # replace appropriate file
            cache_data = data
            self.read_data('Users','UserId',cache_data) # replace appropriate table and keys


            table_list = {'Users':'UserId', 'Classes' :'ClassId', 'Students':'StudentID', 'Enrollments':'EnrollmentID', 
                      'Instructors':'InstructorID', 'InstructorClasses':'InstructorClassesID', 'Freeze':'IsFrozen'}
        '''
        
        return