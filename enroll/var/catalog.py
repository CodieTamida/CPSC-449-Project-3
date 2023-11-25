import boto3
from botocore.exceptions import ClientError
import logging
from datetime import datetime
from decimal import Decimal

from dynamodb_dummy_data import DynamodbData
# Create a DynamoDB resource

logger = logging.getLogger(__name__)


class Dynamodbmodel:

    def __init__(self, dynamodb_resource) -> None:

        self.dynamodb_resource = dynamodb_resource

    def delete_table_if_exists(self):
        
        table_list = ['Users', 'Classes', 'Students', 'Enrollments', 'Instructors', 'InstructorClasses', 'Freeze']
        
        # Get all the existing tables
        table_names = [table.name for table in self.dynamodb_resource.tables.all()]

        for table in table_list:
            if table in table_names:
                t = self.dynamodb_resource.Table(table)
                t.delete()
                print(f"Deleting {t.name}...")
                t.wait_until_not_exists()
        return

    def create_tables(self):

        users_table = self.dynamodb_resource.create_table(
            TableName='Users',
            KeySchema=[
                {'AttributeName': 'UserId', 'KeyType': 'HASH'}
            ],

            AttributeDefinitions=[
                {'AttributeName': 'UserId', 'AttributeType': 'N'},
                {'AttributeName': 'Username', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'UsersIndex',
                    'Projection': {
                        'ProjectionType': 'ALL'
                    },
                    'KeySchema': [
                        {
                            'AttributeName': 'Username',
                            'KeyType': 'HASH'
                        }
                    ],
                    "ProvisionedThroughput": { 
                        "ReadCapacityUnits": 5,
                        "WriteCapacityUnits": 5
                    }
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        users_table.wait_until_exists()
        
        # users_table.put_item(Item={'UserId': 100,'Username':"ornella","Fullname":"Ornella Dsouza","Email":"o@gmail.com"})
        
        # Create Classes table
        classes_table = self.dynamodb_resource.create_table(
            TableName='Classes',
            KeySchema=[
                {'AttributeName': 'ClassID', 'KeyType': 'HASH'},
                {'AttributeName': 'SectionNumber', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'ClassID', 'AttributeType': 'N'},
                {'AttributeName': 'SectionNumber', 'AttributeType': 'N'}
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        classes_table.wait_until_exists()

        # Create Students table
        students_table = self.dynamodb_resource.create_table(
            TableName='Students',
            KeySchema=[
                {'AttributeName': 'StudentID', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'StudentID', 'AttributeType': 'N'}
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        students_table.wait_until_exists()

        # Create Enrollments table
        enrollments_table = self.dynamodb_resource.create_table(
            TableName='Enrollments',
            KeySchema=[
                {'AttributeName': 'EnrollmentID', 'KeyType': 'HASH'}
                # {'AttributeName': 'StudentID', 'KeyType': 'RANGE'} # ADDED
            ],
            AttributeDefinitions=[
                {'AttributeName': 'EnrollmentID', 'AttributeType': 'N'},
                {'AttributeName': 'StudentID', 'AttributeType': 'N'},
                {'AttributeName': 'ClassID', 'AttributeType': 'N'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'EnrollmentsIndex',
                    'Projection': {
                        'ProjectionType': 'ALL'
                    },
                    'KeySchema': [
                        {
                            'AttributeName': 'StudentID',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'ClassID',
                            'KeyType': 'RANGE'
                        }
                    ],
                    "ProvisionedThroughput": { 
                        "ReadCapacityUnits": 5,
                        "WriteCapacityUnits": 5
                    }
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        enrollments_table.wait_until_exists()

        # Create Instructors table
        instructors_table = self.dynamodb_resource.create_table(
            TableName='Instructors',
            KeySchema=[
                {'AttributeName': 'InstructorID', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'InstructorID', 'AttributeType': 'N'}
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        instructors_table.wait_until_exists()

        # Create InstructorClasses table
        instructor_classes_table = self.dynamodb_resource.create_table(
            TableName='InstructorClasses',
            KeySchema=[
                {'AttributeName': 'InstructorClassesID', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'InstructorClassesID', 'AttributeType': 'N'},
                {'AttributeName': 'InstructorID', 'AttributeType': 'N'},
                {'AttributeName': 'ClassID', 'AttributeType': 'N'}
            ],
            GlobalSecondaryIndexes=[
                {
                    
                    'IndexName': 'InstructorClassesIndex',
                    'Projection': {
                        'ProjectionType': 'ALL'
                        },
                    'KeySchema': [
                        {
                            'AttributeName': 'InstructorID',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'ClassID',
                            'KeyType': 'RANGE'
                        }
                    ],
                    "ProvisionedThroughput": { 
                        "ReadCapacityUnits": 5,
                        "WriteCapacityUnits": 5
                    }
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        instructor_classes_table.wait_until_exists()

        # Create Freeze table
        freeze_table = self.dynamodb_resource.create_table(
            TableName='Freeze',
            KeySchema=[
                {'AttributeName': 'FreezeFlag', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'FreezeFlag', 'AttributeType': 'S'}
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        freeze_table.wait_until_exists()

        load_data = {  
                        users_table : 'users.json', 
                        classes_table : 'classes.json', 
                        students_table : 'students.json', 
                        enrollments_table : 'enrollments.json', 
                        instructors_table : 'instructors.json', 
                        instructor_classes_table : 'instructorclasses.json', 
                        freeze_table : 'freeze.json'
                    }

        for table_object, file_name in load_data.items():
            DynamodbData(dynamodb_resource).load_dummy_data(table_object,'jsonData/'+ file_name)

        return

if __name__ == "__main__":
    dynamodb_resource = boto3.resource('dynamodb',
            aws_access_key_id='fakeMyKeyId',
            aws_secret_access_key='fakeSecretAccessKey',
            endpoint_url='http://localhost:5700',
            region_name='us-west-2'
        )
    obj = Dynamodbmodel(dynamodb_resource)
    obj.delete_table_if_exists()
    obj.create_tables()
    
    print("Dynamodb tables dummy data load job completed")