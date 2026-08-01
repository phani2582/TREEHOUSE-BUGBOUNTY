# Borrowing Rate (TEBR)

Treehouse Ethereum Borrowing Rate (TEBR) is a consensus-derived borrowing rate that represents the cost of capital across Ethereum’s decentralized lending markets. By aggregating borrow rates across leading protocols, TEBR provides a transparent and reliable benchmark for pricing risk and informing financial decisions within the Ethereum ecosystem.


# Methodology

TEBR (Treehouse Ethereum Borrowing Rate) is a high-frequency, liquidity-weighted index designed to track prevailing borrow rates across major DeFi protocols in real time.

TEBR Formula can be simplified to:

<figure><img src="/files/tXK9Ul2HJgITNLLqbSyi" alt=""><figcaption></figcaption></figure>

## Market Exclusion Criteria

Only borrow markets with greater than $5 million in available liquidity are considered. This threshold ensures the index reflects rates from markets with meaningful depth and minimizes the influence of illiquid or volatile pools.

## Weighting Scheme

Rates are weighted based on the proportion of available liquidity in each market relative to the total liquidity across all qualifying markets. This liquidity-weighted approach ensures that more liquid markets exert greater influence on the index.

## Update Frequency

TEBR is refreshed every 10 seconds, providing near real-time visibility into lending rate dynamics across the supported protocols and networks.

# Data

## Data Sources

Borrow rate data is aggregated from the following protocols:

* Aave V3
* Morpho
* Spark
* Compound V3
* Euler V2

The index includes pools from 3 networks: Ethereum, Arbitrum, and Base.


# Get Published Rates

## Where can I get the rates?

You can get the published rate from [API](/protocol/borrowing-rate-tebr/get-published-rates/api).&#x20;

## What rates can I get?

Treehouse publishes only the daily spot [TEBR](/protocol/tebr/treehouse-ethereum-borrowing-rate-tebr). For real time TEBR or historical TEBR, please fill up this [google form](https://forms.gle/wUR8LdTBRx8QBk8j9).


# API

## Spot TEBR

### Latest

Endpoint \[GET]

```url
https://api.treehouse.finance/dor/v1/referencer/tebr
```

Response

```json
{
    "data": [
        {
            "date": "2025-04-15 00:00:00",
            "borrowing_average": 2.818840983675533
        }
    ],
}
```

{% hint style="info" %}
API refreshes at 00:00:00 UTC everyday
{% endhint %}

{% hint style="info" %}
⚠️ Note: This endpoint is rate-limited to 100 requests per minute per IP
{% endhint %}