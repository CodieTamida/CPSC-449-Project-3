import sqlite3
import contextlib
import requests

import redis
r = redis.Redis(host='localhost', port=6379, db=0)





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

def check_id_exists_in_table(id_name: str,id_val: int, table_name: str, db: sqlite3.Connection = Depends(get_db)) -> bool:
    """return true if value found, false if not found"""
    vals = db.execute(f"SELECT * FROM {table_name} WHERE {id_name} = ?",(id_val,)).fetchone()
    if vals:
        return True
    else:
        return False

def check_user(id_val: int, username: str, name: str, email: str, roles: list, db: sqlite3.Connection = Depends(get_db)):
    vals = db.execute(f"SELECT * FROM Users WHERE UserId = ?",(id_val,)).fetchone()
    if not vals:
        db.execute("INSERT INTO Users(Userid, Username, FullName, Email) VALUES(?,?,?,?)",(id_val, username, name, email))

        if "Student" in roles:
            db.execute("INSERT INTO Students (StudentId) VALUES (?)",(id_val,))

        if "Instructor" in roles:
            db.execute("INSERT INTO Instructors (InstructorId) VALUES (?)",(id_val,))
        
        db.commit()

### Student related endpoints

@app.get("/list")
def list_open_classes(db: sqlite3.Connection = Depends(get_db)):
    if (db.execute("SELECT IsFrozen FROM Freeze").fetchone()[0] == 1):
        return {"Classes": []}
    
    classes = db.execute(
        "SELECT * FROM Classes WHERE \
            Classes.MaximumEnrollment > (SELECT COUNT(EnrollmentID) FROM Enrollments WHERE Enrollments.ClassID = Classes.ClassID) \
            OR Classes.WaitlistMaximum > (SELECT COUNT(WaitlistID) FROM Waitlists WHERE Waitlists.ClassID = Classes.ClassID)"
    )
    return {"Classes": classes.fetchall()}

@app.post("/enroll/{studentid}/{classid}/{sectionid}/{name}/{username}/{email}/{roles}", status_code=status.HTTP_201_CREATED)
def enroll_student_in_class(studentid: int, classid: int, sectionid: int, name: str, username: str, email: str, roles: str, db: sqlite3.Connection = Depends(get_db)):
    roles = [word.strip() for word in roles.split(",")]
    check_user(studentid, username, name, email, roles, db)
    
    classes = db.execute("SELECT * FROM Classes WHERE ClassID = ?", (classid,)).fetchone()
    if not classes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found")
    
    enrolled = db.execute("SELECT * FROM Enrollments WHERE ClassID = ? AND StudentID = ? AND EnrollmentStatus='ENROLLED'", (classid, studentid)).fetchone()
    if enrolled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Student already enrolled")
    
    class_section = classes["SectionNumber"]
    count = db.execute("SELECT COUNT() FROM Enrollments WHERE ClassID = ?", (classid,)).fetchone()[0]
    #count = r.zcard(f"enroll:{classid}:{sectionid}")
    #waitlist_count = db.execute("SELECT COUNT() FROM Waitlists WHERE ClassID = ?", (classid,)).fetchone()[0]
    waitlist_count = r.zcard(f"waitlist:{classid}:{sectionid}")  # REDIS    
    print(count)
    if count < classes["MaximumEnrollment"]:
        db.execute("INSERT INTO Enrollments(StudentID, ClassID, SectionNumber) VALUES(?,?,?)",(studentid, classid, class_section))
        db.commit()
        return {"message": f"Enrolled student {studentid} in section {class_section} of class {classid}."}
    elif waitlist_count < classes["WaitlistMaximum"]:
        #waitlisted = db.execute("SELECT * FROM Waitlists WHERE StudentID = ? AND ClassID = ?", (studentid, classid)).fetchone()
        waitlisted = r.zscore(f"waitlist:{classid}:{sectionid}", name)  # REDIS
        if waitlisted:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Student already waitlisted")

        #max_waitlist_position = db.execute("SELECT MAX(Position) FROM Waitlists WHERE ClassID = ? AND  SectionNumber = ?",(classid,sectionid)).fetchone()[0]
        max_waitlist_position = r.zcard(f"waitlist:{classid}:{sectionid}")  # REDIS
        print("Position: " + str(max_waitlist_position + 1))
        if not max_waitlist_position: max_waitlist_position = 0

        ########################### REDIS
        r.zadd(f"waitlist:{classid}:{sectionid}", {name: max_waitlist_position + 1}) #REDIS
        db.execute("INSERT INTO Waitlists(StudentID, ClassID, SectionNumber, Position) VALUES(?,?,?,?)",(studentid, classid, class_section, max_waitlist_position + 1))
        db.commit()
        return {"message": f"Enrolled in waitlist {class_section} of class {classid}."}
    else:
        return {"message": f"Unable to enroll in waitlist for the class, reached the maximum number of students"}


@app.delete("/enrollmentdrop/{studentid}/{classid}/{sectionid}/{name}/{username}/{email}/{roles}")
def drop_student_from_class(studentid: int, classid: int, sectionid: int, name: str, username: str, email: str, roles: str, db: sqlite3.Connection = Depends(get_db)):
    roles = [word.strip() for word in roles.split(",")]
    check_user(studentid, username, name, email, roles, db)
    # Try to Remove student from the class
    
    dropped_student = db.execute("SELECT StudentID FROM Enrollments WHERE StudentID = ? AND ClassID = ? AND SectionNumber = ?",(studentid,classid,sectionid)).fetchone()
    if not dropped_student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Student and class combination not found")

    query = db.execute("UPDATE Enrollments SET EnrollmentStatus = 'DROPPED' WHERE StudentID = ? AND ClassID = ?", (studentid, classid))
    db.commit()
    # Add student to class if there are students in the waitlist for this class
    #next_on_waitlist = db.execute("SELECT * FROM Waitlists WHERE ClassID = ? ORDER BY Position ASC", (classid,)).fetchone()
    next_on_waitlist = r.zrange(f"waitlist:{classid}:{sectionid}", 0, 0)  # REDIS
    if next_on_waitlist:
        try:
            ##### ISSUE HERE, NEED TO GET THE STUDENTID FROM THE WAITLIST, ONLY HAVE THE NAME ######
            db.execute("INSERT INTO Enrollments(StudentID, ClassID, SectionNumber,EnrollmentStatus) \
                            VALUES (?, ?, ?,'ENROLLED')", (int(next_on_waitlist[1]), classid, sectionid))
            
            
            #db.execute("DELETE FROM Waitlists WHERE StudentID = ? AND ClassID = ?", (next_on_waitlist['StudentID'], classid))
            removed_score = r.zscore(f"waitlist:{classid}:{sectionid}", name)
            r.zrem(f"waitlist:{classid}:{sectionid}", name)  # REDIS

            ## Update the waitlist positions
            members = r.zrange(f"waitlist:{classid}:{sectionid}", 0, -1, withscores=True)  # REDIS
            for member, score in members:
                if score > removed_score:
                    r.zadd(f"waitlist:{classid}:{sectionid}", {member: score - 1})
            #db.execute("UPDATE Classes SET WaitlistCount = WaitlistCount - 1 WHERE ClassID = ?", (classid,))
            db.commit()
        except sqlite3.IntegrityError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "ErrorType": type(e).__name__, 
                    "ErrorMessage": str(e)
                },
            )
        
        return {"Result": [
            {"Student dropped from class": dropped_student}, 
            {"Student added from waitlist": next_on_waitlist},
        ]}
    return {"Result": [{"Student dropped from class": dropped_student} ]}

@app.delete("/waitlistdrop/{studentid}/{classid}/{sectionid}/{name}/{username}/{email}/{roles}")
def remove_student_from_waitlist(studentid: int, classid: int, sectionid:int, name: str, username: str, email: str, roles: str, db: sqlite3.Connection = Depends(get_db)):
    roles = [word.strip() for word in roles.split(",")]
    check_user(studentid, username, name, email, roles, db)
    #exists = db.execute("SELECT * FROM Waitlists WHERE StudentID = ? AND ClassID = ?", (studentid, classid)).fetchone()
    exists = r.zscore(f"waitlist:{classid}:{sectionid}", name)  # REDIS
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"Error": "No such student found in the given class on the waitlist"}
        )
    removed_score = r.zscore(f"waitlist:{classid}:{sectionid}", name)  # REDIS
    #db.execute("DELETE FROM Waitlists WHERE StudentID = ? AND ClassID = ?", (studentid, classid))
    r.zrem(f"waitlist:{classid}:{sectionid}", name)  # REDIS

    ## Update the waitlist positions
    members = r.zrange(f"waitlist:{classid}:{sectionid}", 0, -1, withscores=True)  # REDIS
    for member, score in members:
        if score > removed_score:
            r.zadd(f"waitlist:{classid}:{sectionid}", {member: score - 1})
    #db.execute("UPDATE Classes SET WaitlistCount = WaitlistCount - 1 WHERE ClassID = ?", (classid,))

    db.commit()
    return {"Element removed": exists}
    
@app.get("/waitlist/{studentid}/{classid}/{sectionid}/{name}/{username}/{email}/{roles}")
def view_waitlist_position(studentid: int, classid: int, sectionid:int, name: str, username: str, email: str, roles: str, db: sqlite3.Connection = Depends(get_db)):
    roles = [word.strip() for word in roles.split(",")]
    check_user(studentid, username, name, email, roles, db)
    position = None
    #position = db.execute("SELECT Position FROM Waitlists WHERE StudentID = ? AND ClassID = ?", (studentid,classid,)).fetchone()
    position = r.zscore(f"waitlist:{classid}:{sectionid}", name)  # REDIS
    
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
def view_enrolled(instructorid: int, classid: int, sectionid: int, name: str, username: str, email: str, roles: str, db: sqlite3.Connection = Depends(get_db)):
    roles = [word.strip() for word in roles.split(",")]
    check_user(instructorid, username, name, email, roles, db)
    instructor_class = db.execute("SELECT * FROM InstructorClasses WHERE classID=? AND SectionNumber=?",(classid,sectionid)).fetchone()
    if not instructor_class:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Instructor does not have this class"
        )

    enrolled_students = db.execute("SELECT StudentID FROM Enrollments WHERE classID=? AND SectionNumber=? AND EnrollmentStatus='ENROLLED'",(classid,sectionid))
    enrolled = enrolled_students.fetchall()
    if enrolled:
        return {"All students enrolled in this instructor's classes" : enrolled}
    else:
        raise HTTPException(
            status_code=status.HTTP_204_NO_CONTENT
        )

@app.get("/dropped/{instructorid}/{classid}/{sectionid}/{name}/{username}/{email}/{roles}")
def view_dropped_students(instructorid: int, classid: int, sectionid: int, name: str, username: str, email: str, roles: str, db: sqlite3.Connection = Depends(get_db)):
    roles = [word.strip() for word in roles.split(",")]
    check_user(instructorid, username, name, email, roles, db)
    instructor_class = db.execute("SELECT * FROM InstructorClasses WHERE classID=? AND SectionNumber=?",(classid,sectionid)).fetchone()
    if not instructor_class:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Instructor does not have this class"
        )
    
    query = "SELECT StudentID FROM Enrollments WHERE ClassID = ? AND SectionNumber = ? AND EnrollmentStatus = 'DROPPED'"
    dropped_students = db.execute(query, (classid, sectionid)).fetchall()
    if not dropped_students:
        raise HTTPException(status_code=404, detail="No dropped students found for this class.")
    return {"Dropped Students ID": [student["StudentID"] for student in dropped_students]}

@app.delete("/drop/{instructorid}/{classid}/{sectionid}/{studentid}/{name}/{username}/{email}/{roles}")
def drop_student_administratively(instructorid: int, classid: int, sectionid:int, studentid: int, name: str, username: str, email: str, roles: str, db: sqlite3.Connection = Depends(get_db)):
    roles = [word.strip() for word in roles.split(",")]
    check_user(instructorid, username, name, email, roles, db)
    instructor_class = db.execute("SELECT * FROM InstructorClasses WHERE classID=?",(classid,)).fetchone()
    if not instructor_class:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Instructor does not have this class"
        )
    
    in_class = db.execute("SELECT * FROM Enrollments WHERE classID=? AND EnrollmentStatus='ENROLLED' AND StudentID=?",(classid, studentid)).fetchone()
    if not in_class:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student is not enrolled"
        )

    query = "UPDATE Enrollments SET EnrollmentStatus = 'DROPPED' WHERE StudentID = ? AND ClassID = ?"
    result = db.execute(query, (studentid, classid))
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Student, class, or section not found.")
    
    # Add student to class if there are students in the waitlist for this class
    #next_on_waitlist = db.execute("SELECT * FROM Waitlists WHERE ClassID = ? ORDER BY Position ASC", (classid,)).fetchone()
    next_on_waitlist = r.zrange(f"waitlist:{classid}:{sectionid}", 0, 0)  # REDIS
    if next_on_waitlist:
        try:
            db.execute("INSERT INTO Enrollments(StudentID, ClassID, SectionNumber,EnrollmentStatus) \
                            VALUES (?, ?, (SELECT SectionNumber FROM Classes WHERE ClassID=?), 'ENROLLED')", (next_on_waitlist['StudentID'], classid, classid))
            #db.execute("DELETE FROM Waitlists WHERE StudentID = ? AND ClassID = ?", (next_on_waitlist['StudentID'], classid))
            r.zrem(f"waitlist:{classid}:{sectionid}", name)  # REDIS
            #db.execute("UPDATE Classes SET WaitlistCount = WaitlistCount - 1 WHERE ClassID = ?", (classid,))

            db.commit()
        except sqlite3.IntegrityError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "ErrorType": type(e).__name__, 
                    "ErrorMessage": str(e)
                },
            )
    return {"message": f"Student {studentid} has been administratively dropped from class {classid}"}

@app.get("/waitlist/{instructorid}/{classid}/{sectionid}/{name}/{username}/{email}/{roles}")
def view_waitlist(instructorid: int, classid: int, sectionid: int, name: str, username: str, email: str, roles: str, db: sqlite3.Connection = Depends(get_db)):
    roles = [word.strip() for word in roles.split(",")]
    check_user(instructorid, username, name, email, roles, db)
    instructor_class = db.execute("SELECT * FROM InstructorClasses WHERE classID=? AND SectionNumber=?",(classid,sectionid)).fetchone()
    if not instructor_class:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Instructor does not have this class"
        )
    
    query = "SELECT * FROM Students INNER JOIN (SELECT StudentID, Position FROM Waitlists WHERE ClassID = ? AND SectionNumber =? ORDER BY Position) as w on Students.StudentID = w.StudentID"
    #waitlist = db.execute(query, (classid, sectionid)).fetchall()
    waitlist = r.zrange(f"waitlist:{classid}:{sectionid}", 0, -1)  # REDIS
    if not waitlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No students found in the waitlist for this class")
    return {"Waitlist": [{"student_id": student["StudentID"]} for student in waitlist]}


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

    class_found = db.execute("SELECT * FROM Classes WHERE ClassID = ? AND SectionNumber = ?",(classid,sectionid)).fetchone()
    if not class_found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Class {classid} Section {sectionid} does not exist in database.")
    db.execute("DELETE FROM Classes WHERE ClassID =? AND SectionNumber =?", (classid, sectionid))
    db.execute("DELETE FROM InstructorClasses WHERE ClassID =? AND SectionNumber =?", (classid, sectionid))
    db.execute("DELETE FROM Enrollments WHERE ClassID =? AND SectionNumber =?", (classid, sectionid))
    db.commit()
    return {"Removed" : f"Course {classid} Section {sectionid}"}

@app.put("/freeze/{isfrozen}", status_code=status.HTTP_204_NO_CONTENT)
def freeze_enrollment(isfrozen: str, db: sqlite3.Connection = Depends(get_db)):
    if (isfrozen.lower() == "true"):
        db.execute("UPDATE Freeze SET IsFrozen = true")
        db.commit()
    elif (isfrozen.lower() == "false"):
        db.execute("UPDATE Freeze SET IsFrozen = false")
        db.commit()
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Freeze must be true or false.")

@app.put("/change/{classid}/{newprofessorid}", status_code=status.HTTP_204_NO_CONTENT)
def change_prof(request: Request, classid: int, newprofessorid: int, db: sqlite3.Connection = Depends(get_db)):
    instructor_req = requests.get(f"http://localhost:{KRAKEND_PORT}/user/get/{newprofessorid}", headers={"Authorization": request.headers.get("Authorization")})
    instructor_info = instructor_req.json()

    if instructor_req.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instructor does not exist",
        )

    check_user(instructor_info["userid"], instructor_info["username"], instructor_info["name"], instructor_info["email"], instructor_info["roles"], db)
    valid_class_id = check_id_exists_in_table("ClassID",classid,"Classes",db)
    if not valid_class_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class does not exist",
        )
    
    try:
        db.execute("UPDATE InstructorClasses SET InstructorID=? WHERE ClassID=?", (instructor_info["userid"], classid))
        db.commit()
    except sqlite3.IntegrityError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"type": type(e).__name__, "msg": str(e)},
        )

