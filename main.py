from bson import ObjectId
from flask import Flask, jsonify, render_template, request, redirect, url_for
from flask_limiter import Limiter
from pymongo import MongoClient
from datetime import datetime
from pymongo.server_api import ServerApi
from datetime import datetime
import pytz



app = Flask(__name__)
uri = 'mongodb+srv://Temp_User:9BH1EM6p6LWStCxt@mongodatabase.ytbk03l.mongodb.net/?retryWrites=true&w=majority'

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)


db = client['quiz_app']
quizzes_collection = db['quizzes']
results_collection = db['results']

# Rate limiting configuration
limiter = Limiter(app, default_limits=["10 per minute"])

def convert_to_ist(datetime_obj):
    ist_timezone = pytz.timezone('Asia/Kolkata')  # IST timezone
    washington_timezone = pytz.timezone('America/New_York')  # Washington, D.C., USA timezone
    washington_datetime = washington_timezone.localize(datetime_obj)
    ist_datetime = washington_datetime.astimezone(ist_timezone)
    return ist_datetime



def adjust_to_washington(datetime_obj):
    ist_timezone = pytz.timezone('Asia/Kolkata')  # IST timezone
    washington_timezone = pytz.timezone('America/New_York')  # Washington, D.C., USA timezone
    ist_datetime = ist_timezone.localize(datetime_obj)
    washington_datetime = ist_datetime.astimezone(washington_timezone)
    return washington_datetime


# Helper function to check if a quiz is active
def is_quiz_active(quiz):
    now = datetime.now()
    return quiz['start_date'] <= now <= quiz['end_date']

# Helper function to update quiz status based on current time
def update_quiz_status():
    now = datetime.now()
    quizzes = quizzes_collection.find()
    for quiz in quizzes:
        if now < quiz['start_date']:
            quiz_status = 'inactive'
        elif now > quiz['end_date']:
            quiz_status = 'finished'
        elif now < quiz['end_date'] and now > quiz['start_date']:
            quiz_status = 'active'
        quizzes_collection.update_one({'_id': quiz['_id']}, {'$set': {'status': quiz_status, 'start_date': quiz['start_date'], 'end_date': quiz['end_date']}})

def update_status_return():
    now = datetime.now()
    quizzes = quizzes_collection.find()
    for quiz in quizzes:
        if now < quiz['start_date']:
            quiz_status = 'inactive'
        elif now > quiz['end_date']:
            quiz_status = 'finished'
        elif now < quiz['end_date'] and now > quiz['start_date']:
            quiz_status = 'active'
        return quiz_status

@app.route('/', methods=['GET','POST'])
def home_page():
    if request.method == 'POST':
        return redirect(url_for('create_quiz'))
    return render_template('index.html')

# Endpoint to create a new quiz
@app.route('/create_quiz', methods=['GET', 'POST'])
@limiter.limit("2 per minute")  # Rate limit: 2 requests per minute
def create_quiz():
    num_questions = 0
    if request.method == 'POST':
        # Retrieve form data and create the quiz
        num_questions = int(request.form['num_questions'])
        quiz_name = request.form['quizName']
        author = request.form['author']
        start_date = request.form['startDate']
        start_time = request.form['startTime']
        end_date = request.form['endDate']
        end_time = request.form['endTime']

        questions = []
        for i in range(1, num_questions + 1):
            question = request.form['question{}'.format(i)]
            options = []
            for j in range(1, 5):
                option = request.form['question{}_option{}'.format(i, j)]
                options.append(option)
            correct_option = int(request.form['question{}_correct_option'.format(i)])
            questions.append({'question': question, 'options': options, 'correct_option': correct_option})

        start_datetime = adjust_to_washington(datetime.strptime(start_date + ' ' + start_time, '%Y-%m-%d %H:%M'))
        end_datetime = adjust_to_washington(datetime.strptime(end_date + ' ' + end_time, '%Y-%m-%d %H:%M'))

        # Insert the new quiz into the database
        stat = update_status_return()
        quiz = {
            'quiz_name': quiz_name,
            'author': author,
            'start_date': start_datetime,
            'end_date': end_datetime,
            'questions': questions,
            'status': stat
        }
        quizzes_collection.insert_one(quiz)

        # Update the quiz status
        update_quiz_status()

        # Redirect to the quizzes page
        return redirect(url_for('get_all_quizzes'))
    else:
        return render_template('create_quiz.html', num_questions=num_questions)


@app.route('/start_quiz/<quiz_id>', methods=['GET'])
@limiter.exempt  # Exempt rate limiting for starting a quiz
def start_quiz(quiz_id):
    quiz = quizzes_collection.find_one({'_id': ObjectId(quiz_id)})
    questions = [{'i': i, **question} for i, question in enumerate(quiz['questions'])]
    return render_template('quiz.html', quiz=quiz, questions=questions)


@app.route('/submit_quiz/<quiz_id>', methods=['POST'])
@limiter.limit("5 per minute")  # Rate limit: 5 requests per minute
def submit_quiz(quiz_id):
    quiz = quizzes_collection.find_one({'_id': ObjectId(quiz_id)})
    questions = [{'i': i, **question} for i, question in enumerate(quiz['questions'])]

    responses = []
    for question in questions:
        response_key = 'response_{}'.format(question['i'])
        response = request.form.get(response_key)
        responses.append(response)
    score = 0
    for i, response in enumerate(responses):
        if response is not None and int(response) == int(quiz['questions'][i]['correct_option']):
            score += 1


    result = {
        'quiz_id': quiz_id,
        'score': score,
        'quiz_name': quiz['quiz_name'],
        'timestamp': datetime.now()
    }
    results_collection.insert_one(result)

    return redirect(url_for('get_all_results'))


@app.route('/quizzes/all', methods=['GET'])
def get_all_quizzes():
    update_quiz_status()
    quizzes = quizzes_collection.find()

    active_quizzes = []
    inactive_quizzes = []
    finished_quizzes = []

    for quiz in quizzes:

        if quiz['status'] == 'active':
            active_quizzes.append(quiz)
        elif quiz['status'] == 'inactive':
            inactive_quizzes.append(quiz)
        elif quiz['status'].lower() == 'finished':
            finished_quizzes.append(quiz)

    return render_template('quizzes.html', activeQuizzes=active_quizzes, inactiveQuizzes=inactive_quizzes, finishedQuizzes=finished_quizzes)

# Endpoint to get all quiz results
@app.route('/results/all', methods=['GET'])
def get_all_results():
    results = results_collection.find()
    return render_template('results.html', results=results)


if __name__ == '__main__':
    app.run()
