#!/usr/bin/env python3

def fix_all_issues():
    with open('src/slack_healthcheck_bot.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix the specific indentation issue around line 3881
    lines = content.split('\n')
    
    # Fix the except statement indentation
    for i, line in enumerate(lines):
        if 'except Exception as e:' in line and 'Error sending unresolved blocker DM' in lines[i+1]:
            # This is the problematic line, fix its indentation
            lines[i] = '                        except Exception as e:'
            break
    
    # Fix other indentation issues
    for i, line in enumerate(lines):
        # Fix lines that should be indented after try statements
        if 'try:' in line and i + 1 < len(lines):
            next_line = lines[i + 1]
            if next_line.strip() and not next_line.startswith('    ') and not next_line.startswith('\t'):
                # Fix common patterns
                if 'user_info = bot.client.users_info' in next_line:
                    lines[i + 1] = '                            ' + next_line.lstrip()
                elif 'bot.send_standup_to_dm' in next_line:
                    lines[i + 1] = '                            ' + next_line.lstrip()
                elif 'bot.send_health_check_to_dm' in next_line:
                    lines[i + 1] = '                            ' + next_line.lstrip()
                elif 'result = bot.send_mentor_check(' in next_line:
                    lines[i + 1] = '                            ' + next_line.lstrip()
                elif 'user_id=user_id,' in next_line:
                    lines[i + 1] = '                                ' + next_line.lstrip()
                elif 'standup_ts=None,' in next_line:
                    lines[i + 1] = '                                ' + next_line.lstrip()
                elif 'user_name=user_name,' in next_line:
                    lines[i + 1] = '                                ' + next_line.lstrip()
                elif 'request_type=' in next_line:
                    lines[i + 1] = '                                ' + next_line.lstrip()
                elif 'channel=user_id' in next_line:
                    lines[i + 1] = '                                ' + next_line.lstrip()
    
    # Write the fixed file
    with open('src/slack_healthcheck_bot.py', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

if __name__ == "__main__":
    fix_all_issues()
    print("All issues fixed!") 