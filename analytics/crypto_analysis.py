import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os
import webbrowser
from datetime import datetime
import warnings
import argparse
warnings.filterwarnings('ignore')

# ========================
# 1. Load the dataset
# ========================
parser = argparse.ArgumentParser(description="Comprehensive crypto analysis charts")
parser.add_argument("--input", required=False, default="exports/alerts_training_2025-09-26_133546.csv", help="Input CSV path")
parser.add_argument("--outdir", required=False, default="data/analysis_charts", help="Output directory for charts")
args = parser.parse_args()

file_path = args.input
df = pd.read_csv(file_path)

# ========================
# 2. Create output folder
# ========================
output_dir = args.outdir
os.makedirs(output_dir, exist_ok=True)

# ========================
# 3. Data preprocessing
# ========================
# Convert datetime columns
df['alerted_at'] = pd.to_datetime(df['alerted_at'])
df['first_alert_at'] = pd.to_datetime(df['first_alert_at'])
df['last_checked_at'] = pd.to_datetime(df['last_checked_at'])

# Handle missing values in outcome column
df['outcome'] = df['outcome'].fillna('ongoing')

# Create performance categories
df['performance_category'] = pd.cut(df['peak_x_price'], 
                                   bins=[0, 1, 2, 5, float('inf')], 
                                   labels=['Loss/Flat', '2x', '5x', '5x+'])

# Create score categories
df['score_category'] = pd.cut(df['final_score'], 
                             bins=[0, 6, 8, 10], 
                             labels=['Low (6-)', 'Medium (7-8)', 'High (9-10)'])

# Set style
plt.style.use('default')
sns.set_palette("husl")

print(f"Dataset loaded: {len(df)} tokens")
print(f"Date range: {df['alerted_at'].min()} to {df['alerted_at'].max()}")
print(f"Outcomes: {df['outcome'].value_counts().to_dict()}")

# ========================
# 4. Plot 1: Performance Distribution by Score
# ========================
plt.figure(figsize=(12, 8))

# Subplot 1: Box plot of peak multipliers by score
plt.subplot(2, 2, 1)
sns.boxplot(data=df, x='final_score', y='peak_x_price', palette='viridis')
plt.title('Peak Price Multiplier by Final Score')
plt.xlabel('Final Score')
plt.ylabel('Peak X Price')
plt.yscale('log')

# Subplot 2: Performance categories by score
plt.subplot(2, 2, 2)
score_perf = pd.crosstab(df['score_category'], df['performance_category'], normalize='index')
score_perf.plot(kind='bar', stacked=True, ax=plt.gca())
plt.title('Performance Distribution by Score Category')
plt.xlabel('Score Category')
plt.ylabel('Proportion')
plt.xticks(rotation=45)
plt.legend(title='Performance', bbox_to_anchor=(1.05, 1), loc='upper left')

# Subplot 3: Smart money detection impact
plt.subplot(2, 2, 3)
smart_money_perf = df.groupby('smart_money_detected')['peak_x_price'].agg(['mean', 'median', 'count'])
smart_money_perf['mean'].plot(kind='bar', color='skyblue', ax=plt.gca())
plt.title('Average Performance: Smart Money vs No Smart Money')
plt.xlabel('Smart Money Detected')
plt.ylabel('Average Peak X Price')
plt.xticks([0, 1], ['No', 'Yes'], rotation=0)

# Subplot 4: Score distribution
plt.subplot(2, 2, 4)
df['final_score'].value_counts().sort_index().plot(kind='bar', color='lightcoral')
plt.title('Distribution of Final Scores')
plt.xlabel('Final Score')
plt.ylabel('Count')

plt.tight_layout()
plt.savefig(os.path.join(output_dir, "performance_analysis.png"), dpi=300, bbox_inches="tight")
plt.close()

# ========================
# 5. Plot 2: Market Dynamics Analysis
# ========================
plt.figure(figsize=(15, 10))

# Subplot 1: Liquidity vs Volume scatter
plt.subplot(2, 3, 1)
sns.scatterplot(data=df, x='last_liquidity_usd', y='last_volume_24h_usd', 
                hue='outcome', size='peak_x_price', sizes=(20, 200))
plt.xscale('log')
plt.yscale('log')
plt.title('Liquidity vs Volume (colored by outcome)')
plt.xlabel('Last Liquidity (USD)')
plt.ylabel('Last 24h Volume (USD)')

# Subplot 2: Market cap progression
plt.subplot(2, 3, 2)
sns.scatterplot(data=df, x='first_market_cap_usd', y='peak_market_cap_usd', 
                hue='final_score', size='smart_money_detected', sizes=(50, 150))
plt.xscale('log')
plt.yscale('log')
plt.title('Market Cap: First vs Peak')
plt.xlabel('First Market Cap (USD)')
plt.ylabel('Peak Market Cap (USD)')

# Subplot 3: Price progression
plt.subplot(2, 3, 3)
sns.scatterplot(data=df, x='first_price_usd', y='peak_price_usd', 
                hue='performance_category', alpha=0.7)
plt.xscale('log')
plt.yscale('log')
plt.title('Price: First vs Peak')
plt.xlabel('First Price (USD)')
plt.ylabel('Peak Price (USD)')

# Subplot 4: Time to peak analysis
plt.subplot(2, 3, 4)
df['time_to_peak_hours'] = df['time_to_peak_price_s'] / 3600
sns.histplot(data=df, x='time_to_peak_hours', hue='performance_category', 
             multiple='stack', bins=20)
plt.title('Time to Peak Price Distribution')
plt.xlabel('Time to Peak (hours)')
plt.ylabel('Count')

# Subplot 5: Drawdown analysis
plt.subplot(2, 3, 5)
df_clean = df.dropna(subset=['peak_drawdown_pct'])
sns.boxplot(data=df_clean, x='outcome', y='peak_drawdown_pct')
plt.title('Peak Drawdown by Outcome')
plt.xlabel('Outcome')
plt.ylabel('Peak Drawdown (%)')
plt.xticks(rotation=45)

# Subplot 6: Volume vs Performance
plt.subplot(2, 3, 6)
sns.scatterplot(data=df, x='peak_volume_24h_usd', y='peak_x_price', 
                hue='outcome', alpha=0.7)
plt.xscale('log')
plt.yscale('log')
plt.title('Peak Volume vs Performance')
plt.xlabel('Peak 24h Volume (USD)')
plt.ylabel('Peak X Price')

plt.tight_layout()
plt.savefig(os.path.join(output_dir, "market_dynamics.png"), dpi=300, bbox_inches="tight")
plt.close()

# ========================
# 6. Plot 3: Risk Analysis
# ========================
plt.figure(figsize=(12, 8))

# Subplot 1: Risk vs Reward scatter
plt.subplot(2, 2, 1)
sns.scatterplot(data=df, x='peak_drawdown_pct', y='peak_x_price', 
                hue='outcome', size='final_score', sizes=(30, 200))
plt.title('Risk vs Reward Analysis')
plt.xlabel('Peak Drawdown (%)')
plt.ylabel('Peak X Price')
plt.yscale('log')

# Subplot 2: Liquidity risk
plt.subplot(2, 2, 2)
df['liquidity_risk'] = df['first_liquidity_usd'] / df['first_market_cap_usd']
sns.boxplot(data=df, x='outcome', y='liquidity_risk')
plt.title('Liquidity Risk by Outcome')
plt.xlabel('Outcome')
plt.ylabel('Liquidity/Market Cap Ratio')
plt.xticks(rotation=45)

# Subplot 3: Score vs Risk
plt.subplot(2, 2, 3)
sns.scatterplot(data=df, x='final_score', y='peak_drawdown_pct', 
                hue='smart_money_detected', alpha=0.7)
plt.title('Score vs Risk (Drawdown)')
plt.xlabel('Final Score')
plt.ylabel('Peak Drawdown (%)')

# Subplot 4: Performance distribution
plt.subplot(2, 2, 4)
df['peak_x_price'].hist(bins=30, alpha=0.7, color='skyblue', edgecolor='black')
plt.axvline(df['peak_x_price'].median(), color='red', linestyle='--', 
            label=f'Median: {df["peak_x_price"].median():.2f}x')
plt.axvline(df['peak_x_price'].mean(), color='orange', linestyle='--', 
            label=f'Mean: {df["peak_x_price"].mean():.2f}x')
plt.title('Distribution of Peak Performance')
plt.xlabel('Peak X Price')
plt.ylabel('Frequency')
plt.legend()
plt.yscale('log')

plt.tight_layout()
plt.savefig(os.path.join(output_dir, "risk_analysis.png"), dpi=300, bbox_inches="tight")
plt.close()

# ========================
# 7. Plot 4: Temporal Analysis
# ========================
plt.figure(figsize=(15, 8))

# Subplot 1: Alerts over time
plt.subplot(2, 3, 1)
df['hour'] = df['alerted_at'].dt.hour
hourly_counts = df['hour'].value_counts().sort_index()
hourly_counts.plot(kind='bar', color='lightblue')
plt.title('Alerts by Hour of Day')
plt.xlabel('Hour')
plt.ylabel('Number of Alerts')
plt.xticks(rotation=0)

# Subplot 2: Performance by time
plt.subplot(2, 3, 2)
hourly_performance = df.groupby('hour')['peak_x_price'].mean()
hourly_performance.plot(kind='bar', color='lightgreen')
plt.title('Average Performance by Hour')
plt.xlabel('Hour')
plt.ylabel('Average Peak X Price')
plt.xticks(rotation=0)

# Subplot 3: Score distribution over time
plt.subplot(2, 3, 3)
df['date'] = df['alerted_at'].dt.date
daily_scores = df.groupby('date')['final_score'].mean()
daily_scores.plot(kind='line', marker='o', color='purple')
plt.title('Average Score Over Time')
plt.xlabel('Date')
plt.ylabel('Average Final Score')
plt.xticks(rotation=45)

# Subplot 4: Success rate by score
plt.subplot(2, 3, 4)
success_rate = df.groupby('final_score').apply(
    lambda x: (x['peak_x_price'] > 1).mean()
)
success_rate.plot(kind='bar', color='gold')
plt.title('Success Rate by Final Score')
plt.xlabel('Final Score')
plt.ylabel('Success Rate (>1x)')
plt.xticks(rotation=0)

# Subplot 5: Smart money impact over time
plt.subplot(2, 3, 5)
smart_money_hourly = df.groupby(['hour', 'smart_money_detected'])['peak_x_price'].mean().unstack()
smart_money_hourly.plot(kind='bar', ax=plt.gca())
plt.title('Smart Money Impact by Hour')
plt.xlabel('Hour')
plt.ylabel('Average Peak X Price')
plt.legend(['No Smart Money', 'Smart Money'])
plt.xticks(rotation=0)

# Subplot 6: Outcome distribution
plt.subplot(2, 3, 6)
outcome_counts = df['outcome'].value_counts()
plt.pie(outcome_counts.values, labels=outcome_counts.index, autopct='%1.1f%%', startangle=90)
plt.title('Outcome Distribution')

plt.tight_layout()
plt.savefig(os.path.join(output_dir, "temporal_analysis.png"), dpi=300, bbox_inches="tight")
plt.close()

# ========================
# 8. Plot 5: Correlation Analysis
# ========================
plt.figure(figsize=(14, 10))

# Select numeric columns for correlation
numeric_cols = ['final_score', 'smart_money_detected', 'first_price_usd', 
                'first_market_cap_usd', 'first_liquidity_usd', 'last_price_usd',
                'last_market_cap_usd', 'last_liquidity_usd', 'last_volume_24h_usd',
                'peak_price_usd', 'peak_market_cap_usd', 'peak_volume_24h_usd',
                'peak_drawdown_pct', 'peak_x_price', 'peak_x_mcap', 
                'time_to_peak_price_s', 'time_to_peak_mcap_s']

corr_data = df[numeric_cols].corr()

# Create correlation heatmap
mask = np.triu(np.ones_like(corr_data, dtype=bool))
sns.heatmap(corr_data, mask=mask, annot=True, cmap='coolwarm', center=0,
            square=True, fmt='.2f', cbar_kws={"shrink": .8})
plt.title('Correlation Matrix of Key Metrics')
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "correlation_analysis.png"), dpi=300, bbox_inches="tight")
plt.close()

# ========================
# 9. Summary Statistics
# ========================
print("\n" + "="*50)
print("CRYPTO TRADING ANALYSIS SUMMARY")
print("="*50)

print(f"\n📊 Dataset Overview:")
print(f"   Total tokens analyzed: {len(df)}")
print(f"   Date range: {df['alerted_at'].min().strftime('%Y-%m-%d %H:%M')} to {df['alerted_at'].max().strftime('%Y-%m-%d %H:%M')}")
print(f"   Smart money detected: {df['smart_money_detected'].sum()} ({df['smart_money_detected'].mean()*100:.1f}%)")

print(f"\n🎯 Performance Metrics:")
print(f"   Average peak multiplier: {df['peak_x_price'].mean():.2f}x")
print(f"   Median peak multiplier: {df['peak_x_price'].median():.2f}x")
print(f"   Best performer: {df['peak_x_price'].max():.2f}x")
print(f"   Success rate (>1x): {(df['peak_x_price'] > 1).mean()*100:.1f}%")

print(f"\n📈 Score Analysis:")
for score in sorted(df['final_score'].unique()):
    score_data = df[df['final_score'] == score]
    print(f"   Score {score}: {len(score_data)} tokens, avg {score_data['peak_x_price'].mean():.2f}x performance")

print(f"\n🚨 Risk Analysis:")
print(f"   Average drawdown: {df['peak_drawdown_pct'].mean():.1f}%")
print(f"   Max drawdown: {df['peak_drawdown_pct'].max():.1f}%")
print(f"   Rug pulls: {len(df[df['outcome'] == 'rug'])} ({len(df[df['outcome'] == 'rug'])/len(df)*100:.1f}%)")

print(f"\n⏰ Timing Insights:")
print(f"   Average time to peak: {df['time_to_peak_price_s'].mean()/3600:.1f} hours")
print(f"   Most active hour: {df['hour'].mode().iloc[0]}:00")
print(f"   Best performing hour: {df.groupby('hour')['peak_x_price'].mean().idxmax()}:00")

print(f"\n✅ All charts saved in: {output_dir}")

# Open the folder
folder_path = os.path.abspath(output_dir)
webbrowser.open(folder_path)
