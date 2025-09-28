import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Load the data
df = pd.read_csv("exports/alerts_training_2025-09-26_133546.csv")

print("="*60)
print("🔍 DATA VALIDATION & ACCURACY ANALYSIS")
print("="*60)

# ========================
# 1. Data Quality Checks
# ========================
print("\n📊 DATA QUALITY CHECKS:")
print(f"Total records: {len(df)}")
print(f"Missing values per column:")
missing_data = df.isnull().sum()
for col, missing in missing_data.items():
    if missing > 0:
        print(f"  {col}: {missing} ({missing/len(df)*100:.1f}%)")

# ========================
# 2. Logical Consistency Checks
# ========================
print("\n🔍 LOGICAL CONSISTENCY CHECKS:")

# Check if peak values are actually peaks
peak_price_issues = df[df['peak_price_usd'] < df['first_price_usd']]
print(f"Peak price < first price: {len(peak_price_issues)} records")

peak_mcap_issues = df[df['peak_market_cap_usd'] < df['first_market_cap_usd']]
print(f"Peak market cap < first market cap: {len(peak_mcap_issues)} records")

# Check if last values are consistent with peak values
last_vs_peak_price = df[df['last_price_usd'] > df['peak_price_usd']]
print(f"Last price > peak price: {len(last_vs_peak_price)} records")

# Check if peak_x_price calculations are correct
calculated_peak_x = df['peak_price_usd'] / df['first_price_usd']
actual_peak_x = df['peak_x_price']
x_price_discrepancies = abs(calculated_peak_x - actual_peak_x) > 0.001
print(f"Peak X price calculation discrepancies: {x_price_discrepancies.sum()} records")

# ========================
# 3. Statistical Anomalies
# ========================
print("\n📈 STATISTICAL ANOMALIES:")

# Check for extreme values
print(f"Peak X price range: {df['peak_x_price'].min():.3f} to {df['peak_x_price'].max():.3f}")
print(f"Peak X price median: {df['peak_x_price'].median():.3f}")
print(f"Peak X price mean: {df['peak_x_price'].mean():.3f}")

# Check for outliers
Q1 = df['peak_x_price'].quantile(0.25)
Q3 = df['peak_x_price'].quantile(0.75)
IQR = Q3 - Q1
outliers = df[(df['peak_x_price'] < Q1 - 1.5*IQR) | (df['peak_x_price'] > Q3 + 1.5*IQR)]
print(f"Outliers in peak X price: {len(outliers)} records")

# ========================
# 4. Time Consistency
# ========================
print("\n⏰ TIME CONSISTENCY CHECKS:")

# Convert to datetime
df['alerted_at'] = pd.to_datetime(df['alerted_at'])
df['first_alert_at'] = pd.to_datetime(df['first_alert_at'])
df['last_checked_at'] = pd.to_datetime(df['last_checked_at'])

# Check if first_alert_at matches alerted_at
time_mismatches = df[df['alerted_at'] != df['first_alert_at']]
print(f"Alert time mismatches: {len(time_mismatches)} records")

# Check if last_checked_at is after first_alert_at
time_order_issues = df[df['last_checked_at'] <= df['first_alert_at']]
print(f"Last checked before first alert: {len(time_order_issues)} records")

# ========================
# 5. Smart Money Detection Analysis
# ========================
print("\n🧠 SMART MONEY DETECTION ANALYSIS:")
if 'smart_money_detected' in df.columns:
    sm_rate = float(df['smart_money_detected'].mean())
    print(f"Smart money detected: {df['smart_money_detected'].sum()}/{len(df)} ({sm_rate*100:.1f}%)")
    if sm_rate == 1.0 or sm_rate == 0.0:
        print("⚠️  WARNING: Smart-money detection saturated at %.1f%%" % (sm_rate*100))
        print("   - Revisit detector thresholds and independent-hints requirement")
else:
    print("Column 'smart_money_detected' missing")

# ========================
# 6. Performance Analysis Validation
# ========================
print("\n🎯 PERFORMANCE ANALYSIS VALIDATION:")

# Check if performance metrics make sense
success_rate = (df['peak_x_price'] > 1).mean()
print(f"Success rate (>1x): {success_rate:.1%}")

# Check if rug pulls have appropriate performance
rug_pulls = df[df['outcome'] == 'rug']
if len(rug_pulls) > 0:
    rug_avg_performance = rug_pulls['peak_x_price'].mean()
    print(f"Rug pulls average performance: {rug_avg_performance:.2f}x")
    
    # Rug pulls should generally have poor performance
    if rug_avg_performance > 1.5:
        print("⚠️  WARNING: Rug pulls showing high performance - data may be inconsistent")

# ========================
# 7. Market Cap vs Price Consistency
# ========================
print("\n💰 MARKET CAP CONSISTENCY:")

# Check if market cap calculations are consistent
df['calculated_first_mcap'] = df['first_price_usd'] * 1000000000  # Assuming 1B supply
df['calculated_peak_mcap'] = df['peak_price_usd'] * 1000000000

first_mcap_diff = abs(df['first_market_cap_usd'] - df['calculated_first_mcap']) / df['first_market_cap_usd']
peak_mcap_diff = abs(df['peak_market_cap_usd'] - df['calculated_peak_mcap']) / df['peak_market_cap_usd']

print(f"Average first market cap difference: {first_mcap_diff.mean():.1%}")
print(f"Average peak market cap difference: {peak_mcap_diff.mean():.1%}")

# ========================
# 8. Data Completeness
# ========================
print("\n📋 DATA COMPLETENESS:")

# Check outcome distribution
outcome_counts = df['outcome'].value_counts()
print("Outcome distribution:")
for outcome, count in outcome_counts.items():
    print(f"  {outcome}: {count} ({count/len(df)*100:.1f}%)")

# Check if ongoing tokens have recent data
ongoing_tokens = df[df['outcome'].isna() | (df['outcome'] == 'ongoing')]
print(f"Ongoing tokens: {len(ongoing_tokens)}")

# ========================
# 9. Potential Data Issues
# ========================
print("\n⚠️  POTENTIAL DATA ISSUES:")

issues_found = []

# Issue 1: 100% smart money detection
if df['smart_money_detected'].mean() == 1.0:
    issues_found.append("100% smart money detection rate (unrealistic)")

# Issue 2: High success rate for rug pulls
if len(rug_pulls) > 0 and rug_pulls['peak_x_price'].mean() > 1.2:
    issues_found.append("Rug pulls showing high performance")

# Issue 3: Missing outcome data
if df['outcome'].isna().sum() > len(df) * 0.5:
    issues_found.append("High percentage of missing outcome data")

# Issue 4: Time inconsistencies
if len(time_order_issues) > 0:
    issues_found.append("Time order inconsistencies detected")

# Issue 5: Calculation discrepancies
if x_price_discrepancies.sum() > 0:
    issues_found.append("Peak X price calculation discrepancies")

if issues_found:
    print("Issues identified:")
    for i, issue in enumerate(issues_found, 1):
        print(f"  {i}. {issue}")
else:
    print("No major data quality issues detected")

# ========================
# 10. Accuracy Assessment
# ========================
print("\n🎯 ACCURACY ASSESSMENT:")

accuracy_score = 100
accuracy_issues = []

# Deduct points for each issue
if df['smart_money_detected'].mean() == 1.0:
    accuracy_score -= 20
    accuracy_issues.append("Unrealistic smart money detection rate")

if len(rug_pulls) > 0 and rug_pulls['peak_x_price'].mean() > 1.2:
    accuracy_score -= 15
    accuracy_issues.append("Rug pulls showing unrealistic performance")

if x_price_discrepancies.sum() > 0:
    accuracy_score -= 10
    accuracy_issues.append("Calculation discrepancies")

if len(time_order_issues) > 0:
    accuracy_score -= 5
    accuracy_issues.append("Time inconsistencies")

if df['outcome'].isna().sum() > len(df) * 0.3:
    accuracy_score -= 10
    accuracy_issues.append("High missing data rate")

print(f"Estimated accuracy score: {max(0, accuracy_score)}/100")

if accuracy_issues:
    print("Accuracy concerns:")
    for issue in accuracy_issues:
        print(f"  • {issue}")

print(f"\n📊 RECOMMENDATIONS:")
print("1. Verify smart money detection criteria and thresholds")
print("2. Cross-check peak price calculations")
print("3. Validate outcome classifications")
print("4. Review data collection methodology")
print("5. Consider data filtering for more reliable analysis")

print("\n" + "="*60)
