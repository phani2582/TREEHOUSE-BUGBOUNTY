# Staking Rate (TESR)

The Treehouse Ethereum Staking Rate (TESR) is an annualized metric that measures the average yield accrued by validators within the Ethereum network by sampling all finalized blocks over a one-day observation period. ESR is derived from the rewards data from the consensus layer (Beacon Chain) and the execution layer.

Developed by Treehouse, TESR serves as a trusted benchmark rate for performance comparison within the Ethereum staking market. TESR offers a reliable reference point for stakeholders looking to construct new financial yield-bearing products and navigate the Ethereum staking landscape.


# Methodology

## Index Calculation

The TESR is calculated at the network level, which represents the average reward paid out to validators during each observation period. Because validators are randomly selected to perform specific roles, the reward rate on a node level is not necessarily the same as the calculated TESR.

The TESR calculation follows a 365.25-day convention to annualize staking rewards, which averages the difference in leap years, as indicated in the formula.

$$
TESR\_n = N\_d \times N\_o \times \frac{\sum\_{i=e\_1}^{e\_n} 8 \times (PA\_i + PSY\_i) + PSL\_i + ER\_i - S\_i}{\frac{1}{n} \times \sum\_{i=e\_1}^{e\_n} EB\_{i-1}}
$$

$$
\begin{align\*}
& TESR\_n: \text{The average annualized TESR based on an observation period of } n \text{ epochs.} \\
& N\_d: \text{The number of days in the year } = 365.25. \\
& N\_o: \text{The number of observation periods in a day } = 1. \\
& n: \text{The number of epochs in the observation period, in this case, } 225. \\
& e\_1, e\_n: \text{The first epoch and the last epoch in the observation period, respectively.} \\
& PA\_i: \text{The total Proposer Attestation Inclusion Rewards (incl. Penalties) for all proposers in the epoch.} \\
& PSY\_i: \text{The total Proposer Sync Inclusion Rewards (incl. Penalties) for all proposers in the epoch.} \\
& PSL\_i: \text{The total Proposer Slashing Inclusion Rewards for all proposers in the epoch.} \\
& ER\_i: \text{The total Execution Layer Rewards, either Priority Fees or MEV reward, across all blocks in the epoch.} \\
& S\_i: \text{The total ETH lost by validators to attester and proposer slashings.} \\
& EB\_{i-1}: \text{The network effective balance at the start of the epoch (or end of the previous epoch).}
\end{align\*}
$$


​
  
TESR_n:The average annualized TESR based on an observation period of n epochs.
N_d:The number of days in the year =365.25.
N_o:The number of observation periods in a day =1.
n:The number of epochs in the observation period, in this case, 225.
e_1,e_n:The first epoch and the last epoch in the observation period, respectively.
PA_i:The total Proposer Attestation Inclusion Rewards (incl. Penalties) for all proposers in the epoch.
PSY_i:The total Proposer Sync Inclusion Rewards (incl. Penalties) for all proposers in the epoch.
PSL_i:The total Proposer Slashing Inclusion Rewards for all proposers in the epoch.
ER_i:The total Execution Layer Rewards, either Priority Fees or MEV reward, across all blocks in the epoch.

S_i:The total ETH lost by validators to attester and proposer slashings.
EB_i−1:The network effective balance at the start of the epoch (or end of the previous epoch).
​
 


## Observation Period

The Observation Period of TESR spans one day (t), defined as the start of the first epoch after UTC 00:00 on day t, ending on the last epoch before UTC 00:00 of the following day, t+1.&#x20;

The period will not be adjusted to local time zones and daylight savings.

## Publication Time

TESR will be published between 00:45 and 01:00 UTC, a 1-hour delay relative to the Observation Period. This adjustment provides a buffer for Treehouse to accommodate the finalization of every block within the Observation Period and to address any [Disruptive Events ](https://app.gitbook.com/o/I1OEgXZzV02IqhsO9Pbj/s/k2ACcq4mcZ10BZJwIqAl/~/changes/123/esr/disruptive-events-to-index-calculations)during the [Pre-publication Reliability Checks](https://app.gitbook.com/o/I1OEgXZzV02IqhsO9Pbj/s/k2ACcq4mcZ10BZJwIqAl/~/changes/123/esr/pre-publication-reliability-checks).


# Data

## Data Sources

TESR is calculated using data from Beaconcha.in.&#x20;

Beaconcha.in is one of the most popular and reputed Ethereum 2.0 explorers. Beaconcha.in indexes and provides data sourced from the consensus and execution layer. The Beaconcha.in API is comprehensive and provides historical data as well as the latest real-time data.

## Data Precision

TESR is published as a percentage rate with the precision of 5 decimal places.

## Data Requirements

To compute the TESR for any observation period, the following information is required:

1. The first and last epochs of the observation period
2. The network effective balance at the start of each epoch
3. The proposer of each slot in all the epochs
4. The execution layer block number in each slot
5. The rewards earned by proposers in the epoch where they proposed
   1. Attestation Inclusion reward
   2. Sync Inclusion reward
   3. Slashing Inclusion reward
6. The execution layer rewards for each block including Priority Fees and MEV Rewards
7. The list of slashed validators in each slot
8. The effective balance of validators at specific epochs

Using the above information, it is possible to compute the consensus layer rewards and slashings, the execution layer rewards and the network effective balance for each epoch in the observation period. These values are aggregated to the level of the observation period to compute the final TESR value.

### Epoch Information

**Source:** [/api/v1/epoch/{epoch}](https://beaconcha.in/api/v1/docs/index.html#/Epoch/get_api_v1_epoch__epoch_)

**Data Description:** Epoch level information such as finalised status, number of blocks, global participation rate, network effective balance, etc.

**Usage:**

1. Retrieve the latest epoch to infer the start-of-day epoch and end-of-day epoch
2. Retrieve network effective balance and slashing counts

### Slots in each Epoch

**Source:** [/api/v1/epoch/{epoch}/slots](https://beaconcha.in/api/v1/docs/index.html#/Epoch/get_api_v1_epoch__epoch__slots)

**Data Description:** Slot level information of every slot in a specified epoch. Includes information such as the proposer, slashing count and the corresponding execution layer information, such as the block number in the slot.

**Usage:**

1. Retrieve the proposer for each slot
2. Retrieve the execution layer block number

### Proposer Inclusion Rewards

**Source:** [/api/v1/validator/{indexOrPubkey}/incomedetailhistory](https://beaconcha.in/api/v1/docs/index.html#/Validator/get_api_v1_validator__indexOrPubkey__incomedetailhistory)

**Data Description:** Epoch level information on the consensus layer rewards and penalties earned by the specified validators. Includes attestation rewards, sync committee rewards, proposer rewards, etc.

**Usage:**

1. Retrieve the proposer inclusion rewards for:
   1. Attestation Inclusion
   2. Sync Inclusion&#x20;
   3. Slashing Inclusion

### Execution Layer Rewards

**Source:** [/api/v1/execution/block/{blockNumber}](https://beaconcha.in/api/v1/docs/index.html#/Execution/get_api_v1_execution_block__blockNumber_)

**Data Description:** Data from the execution layer for each specified block. Includes priority fees, MEV rewards, transaction count, gas used, etc.

**Usage:** Retrieve the rewards earned on execution layer, which is either the priority fees or the MEV rewards

### Attester Slashings

**Source:** [/api/v1/slot/{slot}/attesterslashings](https://beaconcha.in/api/v1/docs/index.html#/Slot/get_api_v1_slot__slot__attesterslashings)

**Data Description:** Provides detailed data on the attestations performed on slots that have had an attestation slashing. It is possible to infer the slashed attesters by searching for the common validator across multiple attestations

**Usage:** Retrieve all the validators that got slashed due to illegal attestation

### Proposer Slashings

**Source:** [/api/v1/slot/{slot}/proposerslashings](https://beaconcha.in/api/v1/docs/index.html#/Slot/get_api_v1_slot__slot__proposerslashings)

**Data Description:** Provides detailed data on the slots that have had a proposer slashing and the proposer that got slashed.&#x20;

**Usage:** Retrieve all the validators that got slashed due to illegal proposing

### Validator Balance History

**Source:** [/api/v1/validator/{indexOrPubkey}/balancehistory](https://beaconcha.in/api/v1/docs/index.html#/Validator/get_api_v1_validator__indexOrPubkey__balancehistory)

**Data Description:** Historical balance of the specified validators for the specified epochs

**Usage:** Retrieve the balance changes for all the validators that got slashed at the epoch where they got slashed


# Disruptive Events To Index Calculations

Disruptive Events To Index Calculations include:

* Ethereum fails to finalize blocks
* Changes to the staking reward mechanism
* Too few validators


# Ethereum Fails to Finalize Blocks

In the event of an Ethereum network outage where the Beacon Chain fails to finalize a block throughout the Observation Period, ESR will be computed using the remaining block data accessible during that observation. However, if a complete outage occurs for the entirety of the Observation Period, ESR will be published with a value of 0.




---

[Next Page](/protocol/llms-full.txt/1)


---


# Changes to the Staking Reward Mechanism

In the event of substantial modifications to the Ethereum network's staking reward mechanism, such as the previous transition from Proof-of-Work (PoW) to Proof-of-Stake (PoS), or the widespread adoption of "MEV-boost" by validators, Treehouse reserves the ultimate authority to amend any mechanisms within this document.


# Too Few Validators

In the event that the number of validators on the Beacon Chain drops below 100,000, Treehouse will assess whether TESR should be terminated. If the decision to discontinue TESR is reached, Treehouse will issue a public announcement specifying the cessation date within 2 weeks of the event.


# Pre-publication Reliability Checks

Pre-publication Reliability Checks include:

* Rate Volatility Check
* ESR Component Sanity Data Check


# Rate Volatility Check

In the event that the TESR undergoes a change exceeding two times the 30-day standard deviation, Treehouse shall conduct a thorough investigation to ascertain the origin of said change, utilizing reputable sources such as [etherscan](https://etherscan.io/) and [beaconcha.in](https://beaconcha.in/). Subsequently, an official announcement will be made on the same day with the reasons behind the volatility.


# TESR Component Sanity Data Check

Sanity check of the data by identifying outliers in the epoch-level data of the underlying components of TESR, such as the consensus rewards, execution layer rewards, etc.&#x20;


# Governance

ESR falls under the purview of Treehouse, entrusted with the responsibility of addressing all matters including but not limited to rate oversight, calculation, compliance, commercial dealings, operations, reportings, risks managements, and enacting policies to alleviate any said risks.&#x20;

Specifically, Treehouse shall be responsible for undertaking the following tasks:

* Rate and Methodology Adjustments
* Monitoring
* Cessation
* Licensing and Distribution

<br>


# Rate and Methodology Adjustments

Treehouse must consistently oversee the Benchmark Methodology to ensure its alignment with the specified objectives. Proposed alterations to the [Calculation Methodology](https://docs.google.com/document/d/1_sXx43OF3-LVrl7uDFIM9Mq_fRYifJCkrQGwaBmC2QQ/edit?tab=t.0#heading=h.f7jt27nfsydc), encompassing the benchmark structure, utilized input data, and all facets of the calculation methodology, require approval from Treehouse. Treehouse also reserves the right to seek input from stakeholders and the broader market regarding any proposed changes to the methodology.


# Monitoring

Treehouse will continue to monitor and evaluate TESR, taking into account relevant factors such as market conditions, network performance, and community sentiment. Additionally, Treehouse will be responsible for addressing any discrepancies in the rate and identifying opportunities for further enhancements.


# Cessation

In the event that TESR is deemed unrepresentative of the Ethereum staking rate due to inadequate input data or systemic changes in related markets, Treehouse will engage with stakeholders to discuss the potential for rate cessation, aiming to mitigate risks associated with unrepresentative benchmark references and facilitate a smooth transition.

If viable alternative arrangements are not feasible, Treehouse may recommend discontinuing TESR, ensuring that stakeholders are provided with a minimum of three months' notice and assistance in exploring alternative reference instruments.

The Rate Administrator will endeavor to identify alternative benchmarks; however, this may not always be possible due to regulatory constraints, market conditions, or the availability of suitable alternatives.

<br>


# Licensing and Distribution

Access to TESR is subject to the completion of an Information License Agreement (ILA) and the necessary Schedules. Parties seeking to subscribe to TESR must contact the Rate Administrator at <sales@treehouse.finance>. Additionally, any commercial utilization of TESR must be authorized by Treehouse.<br>

For more information of Treehouse and TESR, please visit our website [www.treehouse.finance](https://docs.treehouse.finance/protocol/dor-operated-by-treehouse/staking-rate-tesr/governance/www.treehouse.finance) or email <sales@treehouse.finance>


# Decentralization

As part of [Treehouse's roadmap to decentralize](/protocol/about-us/road-to-decentralization), the spot TESR has two phases planned:

* Phase I: All DOR participants, *aka* panelists, to submit the spot rates, which will then be used to reach consensus and published daily. This addresses Treehouse being the single source of truth by decentralizing to multiple parties that independently submit value.
* Phase II: Switch from the centralized source, beaconcha.in's APIs, to getting data directly from the beacon chain nodes, which is then used to calculate the daily TESR value for submission by each panelist. This step decentralizes the data from centralized to public sources.


# How Consensus is Reached?

Treehouse, being the operator for the first DOR — TESR, is responsible for publishing its spot and forward consensus from the submissions made by its panelists. Since it is expected that all the spot submissions are supposed to be same, the spot TESR consensus is a simple median of all the values. For the forwards, a [mean of the panelists' submissions](/protocol/dor/consensus-mechanism) decides the consensus instead.


# Get Published Rates

## Where can I get the rates?

You can get the published rate from two sources:

1. [API](/protocol/dor-operated-by-treehouse/staking-rate-tesr/get-published-rates/api)
2. [Smart Contract](/protocol/dor-operated-by-treehouse/staking-rate-tesr/get-published-rates/smart-contract)

## What rates can I get?

Treehouse publishes these two rates that are open to public:

1. Spot TESR: the latest network [TESR](/protocol/tesr/treehouse-ethereum-staking-rate-tesr).
2. Forward TESR (DOR): the rate that the participating panelists submitted for various tenors.

Both of these rates have latest and historical data available across [different sources](#where-can-i-get-the-rates).


# API

## Spot TESR

### Latest

Endpoint \[GET]

```url
https://data-api.treehouse.finance/last_day_esr
```

Response

```json
[
  {
    "date": "2024-12-17",
    "esr": 0.03233904491551333
  }
]

```

### Historical

Endpoint \[GET]

```url
https://data-api.treehouse.finance/daily_esr?date=eq.2024-12-17
```

Include the date parameter in YYYY-MM-DD format.

Response

```json
[
  {
    "date": "2024-12-17",
    "esr": 0.03233904491551333
  }
]
```

## TESR Forwards (DOR)

### Latest

Endpoint \[GET]

```url
https://data-api.treehouse.finance/rpc/esr_forward_curve
```

Response

```json
[
  {
    "realisation_date": "2024-12-20",
    "consensus_value": 0.02957495
  },
  {
    "realisation_date": "2024-12-26",
    "consensus_value": 0.03311533
  },
  {
    "realisation_date": "2025-01-18",
    "consensus_value": 0.05548116000000001
  }
]
```

### Historical

Endpoint \[GET]

```url
https://data-api.treehouse.finance/rpc/esr_forward_curve?round=1
```

Response

```json
[
  {
    "realisation_date": "2024-12-19",
    "consensus_value": 0.02265045
  },
  {
    "realisation_date": "2024-12-25",
    "consensus_value": 0.038555525
  },
  {
    "realisation_date": "2025-01-17",
    "consensus_value": 0.0152069
  }
]
```


# Smart Contract

Read these [Chainlink ](https://chain.link/tutorials/how-to-read-smart-contract)and [QuickNode](https://www.quicknode.com/guides/ethereum-development/smart-contracts/how-to-interact-with-smart-contracts#interacting-with-smart-contracts-using-etherscan) articles to know how to read and interact with a smart contract.

## Spot TESR

The following smart contracts are currently live:

<table><thead><tr><th width="219">Chain</th><th>Smart Contract Address</th></tr></thead><tbody><tr><td>Sepolia Testnet</td><td><a href="https://sepolia.etherscan.io/address/0xb3710c50a687fe716d6b99eda3288a73cc066cf5#readProxyContract">0xB3710c50A687Fe716D6B99EDa3288a73cC066Cf5</a></td></tr><tr><td>Ethereum Mainnet</td><td><a href="https://etherscan.io/address/0xa1c069c2f77b26a54e9f175fa2eade21c34a94e1#readProxyContract">0xa1c069C2F77B26a54e9F175fA2EADe21c34A94E1</a></td></tr></tbody></table>

{% hint style="info" %}
The above table will be updated as the contract goes live on more blockchains.
{% endhint %}

#### Read Methods

All the relevant methods available to query are summarized below:

| Method                  | Description                                                              |
| ----------------------- | ------------------------------------------------------------------------ |
| `decimals`              | number of decimal points to apply on ESR value                           |
| `ESR_PUBLISH_FREQUENCY` | publish frequency of ESR in seconds                                      |
| `getLatestESR`          | latest ESR published as significant digits                               |
| `getLatestESRDate`      | latest published ESR day as SOD unix timestamp                           |
| `getESRForDate`         | takes UTC unix timestamp as input for any day and returns that day's ESR |
| `getEarliestESRDate`    | earliest published ESR day available for query                           |

## TESR Forwards (DOR)

The following smart contracts are currently live:

<table><thead><tr><th width="219">Chain</th><th>Smart Contract Address</th></tr></thead><tbody><tr><td>Sepolia Testnet</td><td><a href="https://sepolia.etherscan.io/address/0x927894aac9b0f9f8719a421a084de52ea06505d1#readContract">0x927894aAc9B0f9F8719a421A084De52EA06505d1</a></td></tr></tbody></table>

{% hint style="info" %}
The above table will be updated as the contract goes live on more blockchains.
{% endhint %}

#### Read Methods

All the relevant methods available to query are summarized below:

| Method                       | Description                                                                               |
| ---------------------------- | ----------------------------------------------------------------------------------------- |
| `dor`                        | DOR name                                                                                  |
| `decimals`                   | number of decimal points to apply on consensus value                                      |
| `getFirstRoundPublishTime`   | publish time of first consensus round in seconds                                          |
| `getActiveTenors`            | list of current active tenors for this DOR                                                |
| `getActiveTenorsUpdateBlock` | block at which current active tenors were updated                                         |
| `getLatestRound`             | latest published round ID for this DOR                                                    |
| `getLatestRoundPublishTime`  | publish time of latest round ID                                                           |
| `getLatestRoundData`         | latest published consensus round data given an active tenor                               |
| `getRoundDataFromId`         | historical consensus round's data given the round ID and an active tenor as of that round |


# Panelist Submission Guide

{% hint style="info" %}
**Submission Period for Forward Round:** Previous day 23:00 UTC to Today 23:00 UTC \
*Example: If the TESR is published on January 10, 2025, the submission period runs from 23:00 UTC on January 9, 2025, to 23:00 UTC on January 10, 2025.*&#x20;

**Consensus TESR Forward Publish Time:** 23:15 UTC

**Submission Period for Spot Round:** 00:20 UTC to 00:50UTC

**Daily Spot TESR Publish Time:** 01:00 UTC
{% endhint %}

**Step 1: Log in to Your Panelist Terminal Account**

Navigate to the Panelist Terminal login page at <https://dor.treehouse.finance/terminal/login> and enter your credentials to access your account.

<figure><img src="/files/fAyA4lWJUY9i5oNVhMoj" alt=""><figcaption></figcaption></figure>

**Step 2: Access the Submission Hub**

Once logged in, locate and click the **"Submission Hub"** button. The button is highlighted in the red square in the reference image below.

<figure><img src="/files/MgeDhPf6Am2wpHrhti4H" alt=""><figcaption></figcaption></figure>

**Step 3: Input your rate prediction**&#x20;

In the Submission Hub, provide your rate predictions for the following tenors:

* 1-day (1d)
* 7-day (7d)
* 30-day (30d)

After entering your predictions, click the **"Submit"** button to proceed.

{% hint style="info" %}
Tenor is the length of time over which the average rate is predicted. Panelists are expected to predict the average daily TESR rate over 1 day, 7 day and 30 day tenors.\
For example, for the round running from 6th Jan 23:00 UTC to 7th Jan 23:00 UTC:

* The TESR prediction for the 1 day tenor will be the average rate on 8th Jan 00:00 UTC to 9th Jan 00:00 UTC
* The TESR prediction for the 7 day tenor will be the average of daily rates from 8th Jan 00:00 UTC to 15th Jan 00:00 UTC
* The TESR prediction for the 30 day tenor will be the average of daily rates from 8th Jan 00:00 UTC to 7th Feb 00:00 UTC
  {% endhint %}

<figure><img src="/files/YxDNg61k1SlyKWZo9sft" alt=""><figcaption></figcaption></figure>

**Step 4: Confirm Your Submission**

Review your rate predictions and click **"Confirm"** to finalize and lock in your submission.

<figure><img src="/files/HyCr2gNQEnRvKkRmAF2c" alt=""><figcaption></figcaption></figure>

After confirming, you will be able to view the rates you have submitted in the system.

<figure><img src="/files/UB1DU5V46EOnICV4yL5m" alt=""><figcaption></figcaption></figure>
