import json
import asyncio
import sys
import os

# FIX для Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import init_db_pool, close_db_pool, get_db_connection

async def load_questions_from_json(json_file_path: str):
    """Load questions from JSON file into database"""
    
    # Read JSON file
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    profiles_data = data.get('profiles', [])
    
    if not profiles_data:
        print("❌ No profiles found in JSON file")
        return
    
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            
            # Loop through all profiles
            for profile_data in profiles_data:
                # Insert profile
                profile_name = profile_data['profile']
                specialization = profile_data.get('specialization', '')
                
                await cur.execute(
                    "INSERT INTO profiles (name, specialization) VALUES (%s, %s) RETURNING id",
                    (profile_name, specialization)
                )
                profile_id = (await cur.fetchone())[0]
                print(f"\n✅ Created profile: {profile_name} - {specialization} (ID: {profile_id})")
                
                # Insert competencies and questions
                for competency in profile_data['competencies']:
                    competency_name = competency['competency_name']
                    
                    await cur.execute(
                        "INSERT INTO competencies (profile_id, name) VALUES (%s, %s) RETURNING id",
                        (profile_id, competency_name)
                    )
                    competency_id = (await cur.fetchone())[0]
                    print(f"  ✅ Competency: {competency_name} (ID: {competency_id})")
                    
                    # Insert topics and questions
                    for topic in competency['topics']:
                        topic_name = topic['topic_name']
                        
                        await cur.execute(
                            "INSERT INTO topics (competency_id, name) VALUES (%s, %s) RETURNING id",
                            (competency_id, topic_name)
                        )
                        topic_id = (await cur.fetchone())[0]
                        print(f"    ✅ Topic: {topic_name} (ID: {topic_id})")
                        
                        # Insert questions
                        for question in topic['questions']:
                            await cur.execute(
                                """INSERT INTO questions 
                                (topic_id, level, question_text, var_1, var_2, var_3, var_4, correct_answer)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                                (
                                    topic_id,
                                    question['level'],
                                    question['question_text'],
                                    question['var_1'],
                                    question['var_2'],
                                    question['var_3'],
                                    question['var_4'],
                                    question['correct_answer']
                                )
                            )
                        print(f"      ✅ Loaded {len(topic['questions'])} questions")
            
            print(f"\n✅ Successfully loaded all data from {json_file_path}")

async def main():
    """Main function to initialize DB and load questions"""
    print("🚀 Starting database loading...")
    
    # Initialize connection pool
    await init_db_pool()
    
    # Load questions from JSON (путь относительно корня проекта)
    await load_questions_from_json('Questions.json')
    
    # Close pool
    await close_db_pool()
    
    print("\n✅ Done!")

if __name__ == "__main__":
    asyncio.run(main())