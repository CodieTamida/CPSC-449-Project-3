import sqlite3
import contextlib
import requests

#from datatime import datetime
import logging
import boto3
#from botocore.exception import ClientError
from pprint import pprint
from .var import dynamodb_dummy_data 

import redis
r=redis.Redis(host='localhost',port=6379,db=0)



from fastapi import FastAPI, Depends, HTTPException, status, Request
from pydantic_settings import BaseSettings
WAITLIST_MAXIMUM = 15
MAXIMUM_WAITLISTED_CLASSES = 3
KRAKEND_PORT = "5600"

class Settings(BaseSettings, env_file="enroll/.env", extra="ignore"):
    database: str
    logging_config: str

def get_db():
    with contextlib.closing(sqlite3.connect(settings.database)) as db:
        db.row_factory = sqlite3.Row
        yield db

settings = Settings()
app = FastAPI()

dynamodb_resource = boto3.client('dynamodb',
                                 aws_access_key_id='fakeMyKeyId',
                                 aws_secret_access_key ='fakeSecretAccessKey',
                                 endpoint_url ="http://localhost:5700",
                                 region_name='us-west-2')

def check_id_exists_in_table(id_name: str,id_val: int, table_name: str, db: sqlite3.Connection = Depends(get_db)) -> bool:
    """return true if value found, false if not found"""
    vals = db.execute(f"SELECT * FROM {table_name} WHERE {id_name} = ?",(id_val,)).fetchone()
    if vals:
        return True
    else:
        return False


#####DynamoDB check_user function
def check_user(id_val: int, username: str, name: str, email: str, roles: list):
    # Check if user exists in Users table in DynamoDB
    response = dynamodb_resource.execute_statement(
        Statement=f"Select * FROM Users WHERE UserId={id_val}",
        ConsistentRead=True
    )
    if not response['Items']:
        # Insert user into Users table
        dynamodb_resource.execute_statement(
            Statement=f"INSERT INTO Users VALUE {{'UserId':{id_val},'Username':{username},'FullName':{name},'Email':{email}}}",
            ConsistentRead=True

        )
        # Check roles and insert into appropriate table
        if "Student" in roles:
            dynamodb_resource.execute_statement(
                Statement=f"INSERT INTO Students VALUE {{'StudentId':{id_val}}}",
                ConsistentRead=True
            )

        if "Instructor" in roles:
            dynamodb_resource.execute_statement(
                Statement=f"INSERT INTO Instructors VALUE {{'InstructorId':{id_val}}}",
                ConsistentRead=True
            )
        

### Student related endpoints

@app.get("/list")
# def list_open_classes(db: sqlite3.Connection = Depends(get_db)):
#     if (db.execute("SELECT IsFrozen FROM Freeze").fetchone()[0] == 1):
#         return {"Classes": []}
    
#     classes = db.execute(
#         "SELECT * FROM Classes WHERE \
#             Classes.MaximumEnrollment > (SELECT COUNT(EnrollmentID) FROM Enrollments WHERE Enrollments.ClassID = Classes.ClassID) \
#             OR Classes.WaitlistMaximum > (SELECT COUNT(WaitlistID) FROM Waitlists WHERE Waitlists.ClassID = Classes.ClassID)"
#     )
#     return {"Classes": classes.fetchall()}
def list_all_classes():
    response=dynamodb_resource.execute_statement(
        Statement="Select * FROM Classes",
        ConsistentRead=True
    )

    #return response['Items']
    return {"Items":response['Items']}

@app.post("/enroll/{studentid}/{classid}/{sectionid}/{name}/{username}/{email}/{roles}", status_code=status.HTTP_201_CREATED)
def enroll_student_in_class(studentid: int, classid: int, sectionid: int, name: str, username: str, email: str, roles: str, db: sqlite3.Connection = Depends(get_db)):
    roles = [word.strip() for word in roles.split(",")]
    check_user(studentid, username, name, email, roles, db)
    
    # classes = db.execute("SELECT * FROM Classes WHERE ClassID = ?", (classid,)).fetchone()
    # if not classes:
    #     raise HTTPException(
    #         status_code=status.HTTP_404_NOT_FOUND,
    #         detail="Class not found")
    classes=dynamodb_resource.execute_statement(
        Statement=f"Select * FROM Classes WHERE ClassID={classid} AND SectionNumber={sectionid}",
        ConsistentRead=True
    )   
    output=classes['Items'][0]
    print(output)
    if not classes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found")

    enrolled = dynamodb_resource.execute_statement(
        Statement=f"Select * FROM Enrollments WHERE ClassID={classid} AND SectionNumber={sectionid} AND StudentID={studentid} AND EnrollmentStatus='ENROLLED'",
        ConsistentRead=True
    )
    enroll_count=dynamodb_resource.execute_statement(
        Statement=f"Select * FROM Enrollments WHERE ClassID={classid} AND SectionNumber={sectionid}",
        ConsistentRead=True
    )
    enroll_count=len(enroll_count['Items'])
    print("This is enroll_count" + str(enroll_count))
    if enrolled['Items']:
        print("This is enrolled_output" + str(enrolled['Items']))

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Student already enrolled")
    enrolled_output=enrolled['Items']

    if not enrolled_output:
        print('is this executing???')
        enrollments = 0
    else:
        enrollments+=1
   
    if enrolled['Items']:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Student already enrolled")
    
    class_section = classes["Items"][0]["SectionNumber"]
    class_section = int(class_section['N'])
    print(class_section)
    print(sectionid)
    # count = db.execute("SELECT COUNT() FROM Enrollments WHERE ClassID = ?", (classid,)).fetchone()[0]
    count = dynamodb_resource.execute_statement(
        Statement=f"Select * FROM Enrollments WHERE ClassID={classid} and SectionID={sectionid}",
        ConsistentRead=True
    )

    count=int(output['MaximumEnrollment']['N'])
    print("This is the count for max en " +str(count))
    max_waitlist= int(output['WaitlistMaximum']['N'])
    # waitlist_count = db.execute("SELECT COUNT() FROM Waitlists WHERE ClassID = ?", (classid,)).fetchone()[0]
    waitlist_count = r.zcard(f"waitlist{classid}:{sectionid}") #REDIS
    print("This is the count for max en " +str(count))
    # if count < classesnt for ["MaximumEnrollment"]:
    #     db.execute("INSERT INTO Enrollments(StudentID, ClassID, SectionNumber) VALUES(?,?,?)",(studentid, classid, class_section))
    #     db.commit()
    #     return {"message": f"Enrolled student {studentid} in section {class_section} of class {classid}."}
    # print(classes)
    # classes =int(classes["MaximumEnrollment"]['N'])
    # print(classes)
    enrollment_id=dynamodb_resource.execute_statement(
        Statement=f"Select * FROM Enrollments",
        ConsistentRead=True
    )
    enrollment_id=len(enrollment_id['Items'])
    print(enrollment_id)
    enrollment_id+=1
    # enrollment_id = 15
    # user_metadata = dynamodb_resource.execute_statement(
    #     TableName='Enrollments',
    #     Key={'EnrollmentID':{'N':str(enrollment_id)}},
    # )

    if enroll_count < count:
        
        dynamodb_resource.execute_statement(
            Statement=f"INSERT INTO Enrollments VALUE {{'EnrollmentID':{enrollment_id},'StudentID':{studentid},'SectionNumber':{sectionid},'ClassID':{classid},'EnrollmentStatus':'ENROLLED'}}",
        )
        print("Enroll insert")
        enrollments+=1
        print("This is Enrollments" + str(enrollments))
        enrollment_id+=1
        return {"message": f"Enrolled student {studentid} in section {class_section} of class {classid}."}
        
    elif waitlist_count < max_waitlist:
        # waitlisted = db.execute("SELECT * FROM Waitlists WHERE StudentID = ? AND ClassID = ?", (studentid, classid)).fetchone()
        waitlisted = r.zscore(f"waitlist:{classid}:{sectionid}",f"{studentid}") #REDIS
        if waitlisted:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Student already waitlisted")

        # max_waitlist_position = db.execute("SELECT MAX(Position) FROM Waitlists WHERE ClassID = ? AND  SectionNumber = ?",(classid,sectionid)).fetchone()[0]
        max_waitlist_position = r.zcard(f"waitlist:{classid}:{sectionid}") #REDIS
        print("Position: " + str(max_waitlist_position))
        if not max_waitlist_position: max_waitlist_position = 0
        # db.execute("INSERT INTO Waitlists(StudentID, ClassID, SectionNumber, Position) VALUES(?,?,?,?)",(studentid, classid, class_section, max_waitlist_position + 1))
        # db.commit()
        max_waitlist_position+=1

        r.zadd(f"waitlist:{classid}:{sectionid}",{studentid:max_waitlist_position})
        return {"message": f"Enrolled in waitlist {max_waitlist_position} for class {classid} section {sectionid}."}
    else:
        return {"message": f"Unable to enroll in waitlist for the class, reached the maximum number of students"}

@app.delete("/enrollmentdrop/{studentid}/{classid}/{sectionid}/{name}/{username}/{email}/{roles}")
def drop_student_from_class(studentid: int, classid: int, sectionid: int, name: str, username: str, email: str, roles: str, db: sqlite3.Connection = Depends(get_db)):
    roles = [word.strip() for word in roles.split(",")]
    check_user(studentid, username, name, email, roles, db)

    # Try to Remove student from the class
    response = dynamodb_resource.execute_statement(
        Statement=f"Select EnrollmentID FROM Enrollments WHERE StudentID = {studentid} AND ClassID = {classid}  AND SectionNumber={sectionid}"
    )
    try:
        if response.get('Items'):
            enrollment_id = response['Items'][0].get('EnrollmentID', {}).get('N')

            if enrollment_id is not None:
                print(f'EnrollmentID: {enrollment_id}')

                # Attempt to drop the student
                dropped_student = dynamodb_resource.execute_statement(
                    Statement=f"DELETE FROM Enrollments WHERE EnrollmentID = {enrollment_id}"
                )

                if dropped_student:
                    print("Student dropped")
                else:
                    print("Failed to drop the student")
            else:
                # Handle the case where 'EnrollmentID' key is not present in the response
                return {"Result": [{"EnrollmentID not found in the response. Student not enrolled in class"}]}
        else:
            # Handle the case where 'Items' is an empty list
            return {"Result": [{"No enrollment records found. Student not enrolled in class"}]}
    
    except Exception as e:
    # Handle other potential exceptions
        print(f"An error occurred: {e}")

    # Add student to class if there are students in the waitlist for this class
    waitlist_key = f"waitlist:{classid}:{sectionid}"
    waitlist_count = r.zcard(waitlist_key)
    print("People in waitlist:", waitlist_count)

    if waitlist_count > 0:
        # Retrieve one student from the waitlist
        next_on_waitlist = r.zrange(waitlist_key, 0, 0, withscores=True)
        
        if not next_on_waitlist:
            return {"Result": [{"No students on the waitlist"}]}

        next_student = int(next_on_waitlist[0][0])
        print("Next student:", next_student)

        try:
            # Determine the next enrollment ID
            response = dynamodb_resource.execute_statement(
                Statement="SELECT * FROM Enrollments WHERE EnrollmentID >= 0 ORDER BY EnrollmentID DESC ;",
                ConsistentRead=True
            )
            enrollment_ids = [int(item['EnrollmentID']['N']) for item in response['Items']]

            # Find the maximum 'EnrollmentID'
            max_enrollment_id = max(enrollment_ids, default=0) + 1
            print(f"The maximum EnrollmentID is: {max_enrollment_id}")
            
            # Enroll the next student from the waitlist
            dynamodb_resource.put_item(
                TableName="Enrollments",
                Item={
                    "EnrollmentID": {"N": str(max_enrollment_id)},
                    "StudentID": {"N": str(next_student)},
                    "ClassID": {"N": str(classid)},
                    "SectionNumber": {"N": str(sectionid)},
                    "EnrollmentStatus": {"S": "ENROLLED"}
                },
            )

            # Remove the enrolled student from the waitlist in Redis
            r.zrem(waitlist_key, next_student)

            members= r.zrange(waitlist_key, 0, 14, withscores=True)
            print("members:",members)
            for member,score in members:
                if score>1:
                    r.zincrby(waitlist_key, -1, member)

            return {"Result": [
                {"Student added to class": next_student},
                {"EnrollmentID": max_enrollment_id},
            ]}
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "ErrorType": type(e).__name__,
                    "ErrorMessage": str(e)
                },
            )

    return {"Result": [{"No students on the waitlist"}]}


@app.delete("/waitlistdrop/{studentid}/{classid}/{sectionid}/{name}/{username}/{email}/{roles}")
def remove_student_from_waitlist(studentid: int, classid: int,sectionid:int, name: str, username: str, email: str, roles: str, db: sqlite3.Connection = Depends(get_db)):
    roles = [word.strip() for word in roles.split(",")]
    user = db.execute("SELECT * FROM Users WHERE UserId = ?", (studentid,)).fetchone()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    exists=r.zscore(f"waitlist:{classid}:{sectionid}",f"{studentid}") #REDIS
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found in waitlist",
        )
    
    # exists = db.execute("SELECT * FROM Waitlists WHERE StudentID = ? AND ClassID = ?", (studentid, classid)).fetchone()
    # if not exists:
    #     raise HTTPException(
    #         status_code=status.HTTP_400_BAD_REQUEST,
    #         detail={"Error": "No such student found in the given class on the waitlist"}
    #     )
    # db.execute("DELETE FROM Waitlists WHERE StudentID = ? AND ClassID = ?", (studentid, classid))
    removed_score=r.zscore(f"waitlist:{classid}:{sectionid}",f"{studentid}") #REDIS
    r.zrem(f"waitlist:{classid}:{sectionid}",f"{studentid}") #REDIS
    members=r.zrange(f"waitlist:{classid}:{sectionid}",0,-1, withscores=True) #REDIS
    for member,score in members:
        if score>removed_score:
            r.zincrby(f"waitlist:{classid}:{sectionid}",-1,member)
    # db.execute("UPDATE Classes SET WaitlistCount = WaitlistCount - 1 WHERE ClassID = ?", (classid,))
    # db.commit()
    return {"Element removed": exists}
    
@app.get("/waitlist/{studentid}/{classid}/{sectionid}/{name}/{username}/{email}/{roles}")
def view_waitlist_position(studentid: int, classid: int,sectionid:int, name: str, username: str, email: str, roles: str, db: sqlite3.Connection = Depends(get_db)):
    roles = [word.strip() for word in roles.split(",")]
    check_user(studentid, username, name, email, roles)
    position = None
    position = r.zscore(f"waitlist:{classid}:{sectionid}",f"{studentid}") #REDIS
    
    if position:
        message = f"Student {studentid} is on the waitlist for class {classid} in position"
    else:
        message = f"Student {studentid} is not on the waitlist for class {classid}"
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=message,
        )
    return {message: position}
    
### Instructor related endpoints

@app.get("/enrolled/{instructorid}/{classid}/{sectionid}/{name}/{username}/{email}/{roles}")
def view_enrolled(instructorid: int, classid: int, sectionid: int, name: str, username: str, email: str, roles: str):

    instructor_class = dynamodb_resource.execute_statement(
        Statement=f"Select * FROM InstructorClasses WHERE ClassID={classid} AND SectionNumber={sectionid}",
        ConsistentRead=True
        )
    if not instructor_class['Items']:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Instructor does not have this class"
        )
    enrolled_students = dynamodb_resource.execute_statement(
        Statement=f"Select * FROM Enrollments WHERE ClassID={classid} AND SectionNumber={sectionid} AND EnrollmentStatus='ENROLLED'",
        ConsistentRead=True
    )

    if enrolled_students:
        student_ids = [student['StudentID']['N'] for student in enrolled_students['Items']]
        return {"Following Student ids enrolled in instructor's class" : student_ids}
    else:
        raise HTTPException(
            status_code=status.HTTP_204_NO_CONTENT
        )  
    
@app.get("/dropped/{instructorid}/{classid}/{sectionid}/{name}/{username}/{email}/{roles}")
def view_dropped_students(instructorid: int, classid: int, sectionid: int, name: str, username: str, email: str, roles: str):
    
    instructor_class = dynamodb_resource.execute_statement(
        Statement=f"Select * FROM InstructorClasses WHERE ClassID={classid} AND SectionNumber={sectionid}",
        ConsistentRead=True
        )
    if not instructor_class['Items']:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Instructor does not have this class"
        )
    print(instructor_class)
    dropped_students = dynamodb_resource.execute_statement(
        Statement=f"Select * FROM Enrollments WHERE ClassID={classid} AND SectionNumber={sectionid} AND EnrollmentStatus='DROPPED'",
        ConsistentRead=True
    )
    print(dropped_students)
    if dropped_students:
        student_ids = [student['StudentID']['N'] for student in dropped_students['Items']]
        return {"Following Student ids dropped in instructor's class" : student_ids}
    else:
        raise HTTPException(
            status_code=status.HTTP_204_NO_CONTENT
        )  

################# endpoint-8 #################

#Test add to Redis waitlist
@app.post("/test/waitlist/{classid}/{sectionid}/{studentid}")
def add_to_waitlist(classid: int, sectionid: int, studentid: int):
    waitlist_key = f"waitlist:{classid}:{sectionid}"
    waitlist_position = r.zcard(waitlist_key) + 1

    r.zadd(waitlist_key, {studentid: waitlist_position})

    return {"message": f"Student {studentid} has been added to the waitlist for class {classid} section {sectionid} in position {waitlist_position}."}


@app.delete("/drop/{instructorid}/{classid}/{sectionid}/{studentid}/{name}/{username}/{email}/{roles}")
def drop_student_administratively(instructorid: int, classid: int, sectionid: int, studentid: int, name: str, username: str, email: str, roles: str):
    
    # Check if student is enrolled in the class
    in_class = dynamodb_resource.execute_statement(
        Statement=f"SELECT * FROM Enrollments WHERE ClassID={classid} AND SectionNumber={sectionid} AND StudentID={studentid} AND EnrollmentStatus='ENROLLED'",
        ConsistentRead=True
    )
    if not in_class['Items']:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student is not enrolled"
        )
    
    enrollment_id = in_class['Items'][0]['EnrollmentID']['N']
    # Update EnrollmentStatus to DROPPED
    dynamodb_resource.update_item(
        TableName='Enrollments',
        Key={
            'EnrollmentID':{'N':str(enrollment_id)}
        },
        UpdateExpression='SET EnrollmentStatus = :status',
        ExpressionAttributeValues={
            ':status': {'S': 'DROPPED'}
        }

    )
    # Check waitlist for class and section in Redis
    waitlist_key = f"waitlist:{classid}:{sectionid}"

    # Check if there are students in the waitlist
    if r.zcard(waitlist_key) > 0:
        # Get student ID of next student in waitlist
        next_student_id = int(r.zrange(waitlist_key, 0, 0, withscores=False)[0])

        # Remove student from waitlist
        next_student_score = r.zscore(waitlist_key, next_student_id)
        r.zrem(waitlist_key, next_student_id)

        # Decrement position of all students in waitlist with position greater than the student removed
        members = r.zrange(waitlist_key, 0, -1, withscores=True)
        for member, score in members:
            if score > next_student_score:
                r.zincrby(waitlist_key, -1, member)
        

        enrollment_id = dynamodb_resource.execute_statement(
            Statement=f"SELECT * FROM Enrollments",
            ConsistentRead=True
        )
        enrollment_id = len(enrollment_id['Items']) + 1

        # Enroll student in class
        dynamodb_resource.execute_statement(
            Statement=f"INSERT INTO Enrollments VALUE {{'EnrollmentID':{enrollment_id},'StudentID':{next_student_id},'SectionNumber':{sectionid},'ClassID':{classid},'EnrollmentStatus':'ENROLLED'}}",
            ConsistentRead=True
        )
        return {"message": f"Student {studentid} has been administratively dropped from class {classid}, section {sectionid}. Student {next_student_id} has been enrolled in their place from the waitlist."}
    
    return {"message": f"Student {studentid} has been administratively dropped from class {classid}, section {sectionid}. There are no students in the waitlist for this class section."}

################# End of endpoint-8 #################

################# endpoint-9 #################

@app.get("/waitlist/instructor/{instructorid}/{classid}/{sectionid}/{name}/{username}/{email}/{roles}")
def view_waitlist(instructorid: int, classid: int, sectionid: int, name: str, username: str, email: str, roles: str):

    # Check if class exists
    class_exists = dynamodb_resource.execute_statement(
        Statement=f"SELECT * FROM Classes WHERE ClassID={classid} AND SectionNumber={sectionid}",
        ConsistentRead=True
    )
    if not class_exists['Items']:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Class does not exist"
        )
    
    
    # Check if there are students in the waitlist/if waitlist exists
    waitlist_key = f"waitlist:{classid}:{sectionid}"
    if not r.exists(waitlist_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No students found in the waitlist for this class"
        )
    
    # Fetch students from waitlist in Redis
    waitlisted_students = r.zrange(waitlist_key, 0, -1, withscores=False)

    waitlist = []
    for student_id in waitlisted_students:
        students = dynamodb_resource.execute_statement(
            Statement=f"SELECT * FROM Students WHERE StudentID={student_id.decode('utf-8')}",
            ConsistentRead=True
        )
        waitlist.append(students['Items'])

    return {"Waitlist": waitlist}

################# End of endpoint-9 #################

### Registrar related endpoints

@app.post("/add/{classid}/{sectionid}/{professorid}/{enrollmax}/{waitmax}", status_code=status.HTTP_201_CREATED)
def add_class(request: Request, classid: str, sectionid: str, professorid: int, enrollmax: int, waitmax: int, db: sqlite3.Connection = Depends(get_db)):
    instructor_req = requests.get(f"http://localhost:5200/user/get/{professorid}", headers={"Authorization": request.headers.get("Authorization")})
    instructor_info = instructor_req.json()

    if instructor_req.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instructor does not exist",
        )
    check_user(instructor_info["userid"], instructor_info["username"], instructor_info["name"], instructor_info["email"], instructor_info["roles"], db)

    try:
        db.execute("INSERT INTO Classes (ClassID, SectionNumber, MaximumEnrollment, WaitlistMaximum) VALUES(?, ?, ?, ?)", (classid, sectionid, enrollmax, waitmax))
        db.execute("INSERT INTO InstructorClasses (InstructorID, ClassID, SectionNumber) VALUES(?, ?, ?)", (professorid, classid, sectionid))
        db.commit()
    except sqlite3.IntegrityError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "ErrorType": type(e).__name__, 
                "ErrorMessage": str(e)
            },
        )
    return {"New Class Added":f"Course {classid} Section {sectionid}"}

@app.delete("/remove/{classid}/{sectionid}")
def remove_class(classid: str, sectionid: str, db: sqlite3.Connection = Depends(get_db)):
    class_found = dynamodb_resource.execute_statement(
        Statement=f"SELECT * FROM Classes WHERE ClassID = {classid} AND SectionNumber = {sectionid}"
    )

    if not class_found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Class {classid} Section {sectionid} does not exist in the database."
        )

    # Delete from Classes table
    delete_statement1 = dynamodb_resource.execute_statement(
        Statement=f"DELETE FROM Classes WHERE ClassID = {classid} AND SectionNumber = {sectionid}",
        ConsistentRead=True
    )

    # Delete from InstructorClasses table
    delete_statement2 = dynamodb_resource.execute_statement(
        Statement=f"SELECT InstructorClassesID FROM InstructorClasses WHERE ClassID = {classid} AND SectionNumber = {sectionid}",
        ConsistentRead=True
    )
    instructor_classes_id = delete_statement2['Items'][0]['InstructorClassesID']['N']
    print(instructor_classes_id)

    dropped_student = dynamodb_resource.execute_statement(
        Statement = f"DELETE from InstructorClasses where InstructorClassesID = {instructor_classes_id}"
    )

    # Get EnrollmentIDs
    enrolled = dynamodb_resource.execute_statement(
        Statement=f"SELECT EnrollmentID FROM Enrollments WHERE ClassID = {classid} AND SectionNumber = {sectionid}",
        ConsistentRead=True
    )

    response = dynamodb_resource.execute_statement(
        Statement=f"SELECT EnrollmentID FROM Enrollments WHERE EnrollmentID >= 0 and ClassID = {classid} AND SectionNumber = {sectionid} ORDER BY EnrollmentID DESC ;",
        ConsistentRead=True
    )
    enrollment_ids = [int(item['EnrollmentID']['N']) for item in response['Items']]
    print("enrolled:",enrollment_ids)

    # Delete from Enrollments table using EnrollmentIDs
    for enrollment_id in enrollment_ids:
        dynamodb_resource.execute_statement(
            Statement=f"DELETE FROM Enrollments WHERE EnrollmentID = {enrollment_id}",
            ConsistentRead=True
        )
    
    waitlist_key = f"waitlist:{classid}:{sectionid}"

    # Delete the specific waitlist key
    r.delete(waitlist_key)

    return {"Removed": f"Course {classid} Section {sectionid}"}

@app.put("/freeze/{isfrozen}")
def freeze_enrollment(isfrozen: int):

    if isfrozen in [0,1]:
        response = dynamodb_resource.execute_statement(
            Statement=f"UPDATE Freeze SET IsFrozen = {isfrozen} Where FreezeFlag = 'Current_Status'",
            ConsistentRead=True
        )
        return "Success"  
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="isfrozen must be 0 or 1.")

@app.put("/change/{classid}/{sectionnumber}/{newprofessorid}", status_code=status.HTTP_204_NO_CONTENT)
def change_prof(request: Request, classid: int, sectionnumber: int, newprofessorid: int, db: sqlite3.Connection = Depends(get_db)):
    instructor_req = requests.get(f"http://localhost:{KRAKEND_PORT}/user/get/{newprofessorid}", headers={"Authorization": request.headers.get("Authorization")})
    instructor_info = instructor_req.json()

    if instructor_req.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instructor does not exist",
        )

    # These functions might need to get updated since the use sqlite.
    # check_user(instructor_info["userid"], instructor_info["username"], instructor_info["name"], instructor_info["email"], instructor_info["roles"], db)
    # valid_class_id = check_id_exists_in_table("ClassID",classid,"Classes",db)
    # if not valid_class_id:
    #     raise HTTPException(
    #         status_code=status.HTTP_404_NOT_FOUND,
    #         detail="Class does not exist",
    #     )
    
    try:
        response=dynamodb_resource.execute_statement(
            Statement=f"Select * FROM InstructorClasses WHERE ClassID={classid} AND SectionNumber={sectionnumber}")
        
        instructor_classes_id = response['Items'][0]['InstructorClassesID']['N']
        print(instructor_classes_id)

        dynamodb_resource.execute_statement(
            Statement=f"Update InstructorClasses SET InstructorID={newprofessorid} WHERE InstructorClassesID={instructor_classes_id}")

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"type": type(e).__name__, "msg": str(e)},
        )
