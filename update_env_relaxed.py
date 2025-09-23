#!/usr/bin/env python3
"""
Script to update .env file with relaxed settings for more bot activity.
"""

import os

def update_env_file():
    """Update .env file with relaxed settings."""
    
    # Read current .env file
    env_file = ".env"
    if not os.path.exists(env_file):
        print(f"Error: {env_file} not found")
        return
    
    # Read current content
    with open(env_file, 'r') as f:
        content = f.read()
    
    # Define relaxed settings
    relaxed_settings = {
        "MIN_LP_SOL": "0.1",
        "MAX_LP_SOL": "2000", 
        "MAX_TOKENS_PER_HOUR": "200",
        "MIN_SCORE_THRESHOLD": "1",
        "SCORE_THRESHOLD": "1",
        "MAX_TOKEN_AGE_HOURS": "168",
        "DEDUP_TTL_S": "300",
        "PUBLISH_DEDUP_TTL_S": "60",
        "DS_MAX_CONCURRENCY": "10",
        "DS_DELAY_S": "0.1",
        "MAX_TRANSFER_TAX_PCT": "20"
    }
    
    # Update each setting
    for key, value in relaxed_settings.items():
        # Find the line with this setting
        lines = content.split('\n')
        updated = False
        
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                updated = True
                break
        
        if not updated:
            # Add new setting if not found
            lines.append(f"{key}={value}")
    
    # Write updated content
    updated_content = '\n'.join(lines)
    with open(env_file, 'w') as f:
        f.write(updated_content)
    
    print("✅ Updated .env file with relaxed settings:")
    for key, value in relaxed_settings.items():
        print(f"  {key}={value}")

if __name__ == "__main__":
    update_env_file()
