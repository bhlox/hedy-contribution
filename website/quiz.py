import json
import uuid
from flask_babel import gettext
from website import statistics
from website.auth import current_user
import utils
from flask import request, g, session, jsonify

MAX_ATTEMPTS = 2

ANSWER_PARSER = {
    1: 'A',
    2: 'B',
    3: 'C',
    4: 'D',
    5: 'E',
    6: 'F'
}

REVERSE_ANSWER_PARSER = {
    'A': 1,
    'B': 2,
    'C': 3,
    'D': 4,
    'E': 5,
    'F': 6
}


def routes(app, database, achievements, quizzes):
    global DATABASE
    global ACHIEVEMENTS
    global QUIZZES

    DATABASE = database
    ACHIEVEMENTS = achievements
    QUIZZES = quizzes

    @app.route('/quiz/initialize_user', methods=['POST'])
    def initialize_user():
        body = request.json
        if not isinstance(body, dict):
            return gettext('ajax_error'), 400
        if not isinstance(body.get('level'), int):
            return gettext('level_invalid'), 400

        session['quiz-attempt-id'] = uuid.uuid4().hex
        session['attempt'] = 0
        session['total_score'] = 0
        session['correctly_answered_questions_numbers'] = []

        statistics.add(current_user()['username'], lambda id_: DATABASE.add_quiz_started(id_, body.get('level')))

        return jsonify({}), 200

    @app.route('/quiz/get-question/<int:level>/<int:question>', methods=['GET'])
    def get_quiz_question(level, question):
        session['attempt'] = 0
        if question > QUIZZES[g.lang].get_highest_question_level(level) or question < 1:
            return gettext('question_doesnt_exist'), 400

        question = QUIZZES[g.lang].get_quiz_data_for_level_question(level, question, g.keyword_lang)
        return jsonify(question), 200

    @app.route('/quiz/submit_answer/', methods=["POST"])
    def submit_answer():
        body = request.json
        if not isinstance(body, dict):
            return gettext('ajax_error'), 400
        if not isinstance(body.get('level'), str):
            return gettext('level_invalid'), 400
        if not isinstance(body.get('question'), str):
            return gettext('question_invalid'), 400
        if not isinstance(body.get('answer'), int):
            return gettext('answer_invalid'), 400

        level = int(body['level'])
        question_number = int(body['question'])

        session['attempt'] += 1

        if session.get('attempt') > MAX_ATTEMPTS:
            return gettext('too_many_attempts'), 400

        if question_number > QUIZZES[g.lang].get_highest_question_level(level) or question_number < 1:
            return gettext('question_doesnt_exist'), 400


        question = QUIZZES[g.lang].get_quiz_data_for_level_question(level, question_number, g.keyword_lang)
        is_correct = True if question['correct_answer'] == ANSWER_PARSER.get(body.get('answer')) else False

        username = current_user()['username'] or f'anonymous:{utils.session_id()}'
        answer = ANSWER_PARSER.get((body.get('answer')))
        DATABASE.record_quiz_answer(session['quiz-attempt-id'], username=username, level=level,
                                    is_correct=is_correct, question_number=question_number,
                                    answer=answer)

        response = {
            'question_text': question.get("question_text"),
            'level': level,
            'attempt': session.get('attempt'),
            'correct_answer_text': question.get("mp_choice_options")[REVERSE_ANSWER_PARSER.get(question.get('correct_answer'))-1].get('option'),
            'feedback': question.get("mp_choice_options")[body.get('answer') - 1].get('feedback'),
            'max_question': QUIZZES[g.lang].get_highest_question_level(level),
            'next_question': True if question_number < QUIZZES[g.lang].get_highest_question_level(level) else False
        }

        if is_correct:
            response['correct'] = True
            score = int(correct_answer_score(question))
            correct_question_nrs = get_correctly_answered_question_nrs()
            if body.get('question') not in correct_question_nrs:
                session['total_score'] = session.get('total_score', 0) + score
                session['correctly_answered_questions_numbers'].append(body.get('question'))
        else:
            response['correct'] = False

        return jsonify(response), 200

    @app.route('/quiz/get_results/<level>', methods=['GET'])
    def get_results(level):
        level = int(level)
        questions = QUIZZES[g.lang].get_quiz_data_for_level(level, g.keyword_lang)

        achievement = None
        total_score = round(session.get('total_score', 0) / max_score(questions) * 100)
        response = {
            'score': total_score,
        }

        username = current_user()['username']
        if username:
            statistics.add(username, lambda id_: DATABASE.add_quiz_finished(id_, level, total_score))
            achievement = ACHIEVEMENTS.add_single_achievement(username, "next_question")
            if total_score == max_score(questions):
                if achievement:
                    achievement.append(ACHIEVEMENTS.add_single_achievement(username, "quiz_master")[0])
                else:
                    achievement = ACHIEVEMENTS.add_single_achievement(username, "quiz_master")
            if achievement:
                response['achievement'] = json.dumps(achievement)

        print(response)
        return jsonify(response), 200


def correct_answer_score(question):
    return question['question_score']


def max_score(quiz_data):
    index = 1
    max_score = 0
    for question_key, question_value in quiz_data.items():
        index = index + 1
        max_score = max_score + int(question_value['question_score'])
    return max_score


def get_correctly_answered_question_nrs():
    if 'correctly_answered_questions_numbers' not in session:
        session['correctly_answered_questions_numbers'] = list()
    return session['correctly_answered_questions_numbers']