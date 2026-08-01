# Lending Rate (TELR)

Treehouse Ethereum Lending Rate (TELR) is a market-driven interest rate that reflects the cost of supplying liquidity across major Ethereum lending protocols. By aggregating lending rates across leading protocols, TELR serves as a benchmark for capital efficiency, helping protocols, traders, and risk managers assess real-time market conditions and optimize yield strategies.


# Methodology

TELR (Treehouse Ethereum Lending Rate) is a high-frequency, liquidity-weighted index designed to track prevailing lending rates across major DeFi protocols in real time.

TELR Formula can be simplified to:

<figure><img src="/files/sDw6bhTkhfrqDrRLV10F" alt=""><figcaption></figcaption></figure>

## Market Exclusion Criteria

Only lending markets with greater than $5 million in available liquidity are considered. This threshold ensures the index reflects rates from markets with meaningful depth and minimizes the influence of illiquid or volatile pools.

## Weighting Scheme

Rates are weighted based on the proportion of available liquidity in each market relative to the total liquidity across all qualifying markets. This liquidity-weighted approach ensures that more liquid markets exert greater influence on the index.

## Update Frequency

TELR is refreshed every 10 seconds, providing near real-time visibility into lending rate dynamics across the supported protocols and networks.


# Data

## Data Sources

Lending rate data is aggregated from the following protocols:

* Aave V3
* Morpho
* Spark
* Compound V3
* Euler V2

The index includes pools from 3 networks: Ethereum, Arbitrum, and Base.


# Get Published Rates

## Where can I get the rates?

You can get the published rate from [API](/protocol/lending-rate-telr/get-published-rates/api).&#x20;

## What rates can I get?

Treehouse publishes only the daily spot [TELR](/protocol/telr/treehouse-ethereum-lending-rate-telr). For real time TELR or historical TELR, please fill up this [google form](https://forms.gle/wUR8LdTBRx8QBk8j9).


# API

## Spot TELR

### Latest

Endpoint \[GET]

```url
https://api.treehouse.finance/dor/v1/referencer/telr
```

Response

```json
{
    "data": [
        {
            "date": "2025-04-15 00:00:00",
            "lending_average": 2.3848756050571094
        }
    ]
}
```

{% hint style="info" %}
API refreshes at 00:00:00 UTC everyday
{% endhint %}

{% hint style="info" %}
⚠️ Note: This endpoint is rate-limited to 100 requests per minute per IP
{% endhint %}