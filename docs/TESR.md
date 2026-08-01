# Treehouse Ethereum Staking Rate (TESR)

The Treehouse Ethereum Staking Rate (TESR) is an annualized metric that measures the average yield accrued by validators within the Ethereum network by sampling all finalized blocks over a one-day observation period. ESR is derived from the rewards data from the consensus layer (Beacon Chain) and the execution layer.

Developed by Treehouse, TESR serves as a trusted benchmark rate for performance comparison within the Ethereum staking market. TESR offers a reliable reference point for stakeholders looking to construct new financial yield-bearing products and navigate the Ethereum staking landscape.

<br>


# Ethereum’s Proof of Stake (PoS) Mechanism

Ethereum staking is the process whereby “validators” or “stakers” commit Ether (ETH) to fortify the security of the Ethereum blockchain. The Ethereum PoS consensus mechanism incentivizes validators with ETH rewards for their participation in the process. Depending on the role in any given block, validators who successfully perform their duties receive a share of the ETH staking rewards based on a predetermined mechanism. However, validators who engage in undesirable behaviors, such as failing to validate transactions properly, being offline for extended periods, or attempting to cheat the system, are penalized. In such cases, a portion of their staked ETH is taken away as a penalty. This penalty serves as a deterrent for malicious activity and encourages validators to act in the network's best interest. The specific nature of the misbehavior determines the severity of the penalty, and in extreme cases, a validator may lose a significant portion of their staked ETH.


# Consensus Layer Rewards

Consensus Layer Rewards consists of 3 different rewards:

* Attestation Rewards
* Sync Committee Rewards
* Proposer Rewards


# Attestation Rewards

Attestation rewards are incentives given to attesting validators. These validators perform actions that are required to create, sign, and broadcast attestations during each epoch. Attestors serve the purpose of voting for the overall validator's view of the blockchain, specifically the most recent justified block and the first block in the current epoch.

Attestation rewards form the largest portion of consensus layer rewards. Despite the randomization of committee and slot assignments for attesting, every active validator will be selected to make precisely one attestation per epoch.&#x20;

<br>


# Sync Committee Rewards

Sync committee rewards are incentives provided to validators participating in the sync committee, a specialized group that allows Ethereum light clients to track the head of the beacon chain’s blocks without needing to access the entire validator set.

Sync committee members are randomly selected once every 256 epochs to receive rewards during the period of participation.

<br>


# Proposer Rewards

Proposer rewards are incentives given to a single validator that is selected to propose the block in each slot, occurring roughly every twelve seconds. The block proposer broadcasts a signed beacon block building upon the most recent head of the chain which includes various data like “RANDAO reveal”, “eth1\_data”, and “graffiti”, to form a “BeaconBlockBody.”

The selection for block proposal happens pseudo-randomly where the probability scales based on the validator’s effective balance at the beginning of each slot.

<br>


# Execution Layer Rewards

Execution Layer Rewards consists of:&#x20;

* Priority Fees/Tips
* Maximal Extractable Value (MEV) Bribes


# Priority Fees/Tips

Priority fee is a new concept introduced with the implementation of [EIP-1559](https://consensys.io/blog/what-is-eip-1559-how-will-it-change-ethereum) on August 5th 2021. Since going live, gas fees on the Ethereum network consist of a base fee (protocol-defined) and a priority fee (user-defined tip) to incentivize validators to include their transactions in the next block.&#x20;

Priority fees will be paid to a predefined address on the Execution Layer chosen by the block’s proposer if the validator does not run a MEV-boost software with their general Ethereum validator client.&#x20;

<br>


# Maximal Extractable Value (MEV) Bribes

Maximal Extractable Value (MEV) is a concept that describes the maximum value that can be extracted from the block production process beyond the standard block reward and gas fees paid by the inclusion, exclusion, and re-ordering of transactions within a block.&#x20;

MEV opportunities can arise in various ways, including but not limited to DEX arbitrage, liquidations in lending protocols, and sandwich trading. While MEV plays a role in optimizing DeFi protocols by correcting economic inefficiencies, there are potential negative consequences, such as increased slippage and network congestion.

The economics of MEV is complex and generally includes 4 parties: users, searchers, builders, and proposers.&#x20;

1. Users: Typical users of the Ethereum network that submit transactions to the public mempool to be confirmed.
2. Searchers: Sophisticated users or bots that identify and create transactions aiming to capitalize on MEV opportunities. The goal of a Searcher is to minimize gas fees and maximize MEV profits as Searchers have to pay a competitive bribe in order to incentivize Builders to select their transactions to be included in the final block.&#x20;
3. Builders: A new role in the MEV supply chain introduced after 'The Merge' with the implementation of [proposer-builder-separation (PBS)](https://ethereum.org/nl/roadmap/pbs). Builders are sophisticated users or bots that construct blocks by taking the bundle of transactions provided by Searchers, along with regular transactions from Users, to form a candidate block that is subsequently forwarded to the proposer using an MEV relay. Their goal is to create the most profitable block for Proposers as Proposers are unable to see transactions within a block.
4. Proposers: Block proposers on the consensus layer who receive a cut of the MEV profits in the form of bribes, on top of the normal staking rewards. Historically, block Proposers earn the majority of the MEV profits in the MEV lifecycle because the markets for Searchers and Builders are extremely competitive.

Notably, the acceptance of MEV rewards is entirely voluntary by validators who wish to participate in the MEV supply chain. In reality, [the majority of validators](https://mevboost.pics/) run MEV-boost software. If a validator decides to run the MEV-boost software and is selected as the Proposer for a block, they will receive the MEV bribes if the block qualifies as an MEV block. Meanwhile, the priority fees that the proposer typically receives will instead be directed to the Builders. This redirection is achieved by modifying the fee recipient address to that of the builder's address using the proposer's validator client.


# Observation Period

The Observation Period of TESR spans one day (t), defined as the start of the first epoch after UTC 00:00 on day t, ending on the last epoch before UTC 00:00 of the following day, t+1.&#x20;

The period will not be adjusted to local time zones and daylight savings.

<br>


# Publication Time

TESR will be published between 00:45 and 01:00 UTC, a 1-hour delay relative to the Observation Period. This adjustment provides a buffer for Treehouse to accommodate the finalization of every block within the Observation Period and to address any [Disruptive Events ](https://app.gitbook.com/o/I1OEgXZzV02IqhsO9Pbj/s/k2ACcq4mcZ10BZJwIqAl/~/changes/123/esr/disruptive-events-to-index-calculations)during the [Pre-publication Reliability Checks](https://app.gitbook.com/o/I1OEgXZzV02IqhsO9Pbj/s/k2ACcq4mcZ10BZJwIqAl/~/changes/123/esr/pre-publication-reliability-checks).


# Index Calculation

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


# Data Precision

TESR is published as a percentage rate with the precision of 5 decimal places.


# Data Sources

TESR is calculated using data from Beaconcha.in.&#x20;

Beaconcha.in is one of the most popular and reputed Ethereum 2.0 explorers. Beaconcha.in indexes and provides data sourced from the consensus and execution layer. The Beaconcha.in API is comprehensive and provides historical data as well as the latest real-time data.

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


# SDK Guide

This SDK package serves as the tool to replicate the ESR computation method followed by Treehouse. The ESR computation involves two steps:

1. Retrieving on-chain data from beaconcha.in for each epoch in the observation period
2. Calculate the average ESR for the observation period according to the formula defined by Treehouse

This package allows the user to perform the same retrieval step and stores the data into a CSV file. The data from file can then be used to calculate ESR.

The package also allows a panelist user to submit their ESR forward prediction using their Treehouse login.

**Getting Started**

**Step 1: Install the SDK**

Run this code:&#x20;

```
pip install git+ssh://git@github.com/treehouse-gaia/dor-python
```

{% hint style="info" %}
The SDK is a private repo, get invited, if you aren't already, by contacting [support](mailto:support@treehouse.finance).
{% endhint %}

**Step 2: Install Required Dependencies**

Run this code:&#x20;

```
pip install -r requirements.txt
```

**Step 3: Add your beachoncha.in API key**

Add your beachoncha.in API key into the BEACONCHA\_API\_KEY under const.py&#x20;

<figure><img src="/files/s5tFyV8WJg5cPmMnatcB" alt=""><figcaption></figcaption></figure>

**Step 4: To get data from the beaconcha.in API, call esr\_live\_job function**

Call the esr\_live\_job function using the code below:&#x20;

```
from dor import esr_live_job
esr_live_job('esr_data.csv')
```

It will output a file called 'esr\_data.csv' with the data from beaconcha.in API

<figure><img src="/files/NpHJsoNDoxnWbGiHXtOC" alt=""><figcaption></figcaption></figure>

**Step 5: To calculate the daily ESR, call calc\_daily\_esr function**

Call the calc\_daily\_esr function with the output file from Step 3 using the code below:

```
from dor import calc_daily_esr
calc_daily_esr('esr_data.csv')
```

It will output the daily ESR

**Step 5: To submit a prediction, call submit\_predictions**

Add your login email address into 'login\_email' and add your login password into 'login\_password' under const.py

<figure><img src="/files/03esmSgT4kAPrWvszm4y" alt=""><figcaption></figcaption></figure>

Input your panelist terminal email, panelist terminal password, your 1d ESR rate prediction, your 7d ESR rate prediction, 30d ESR rate prediction and then run the code:

```
from dor import submit_predictions
submit_predictions(
    {
        "login_email": "your email",
        "login_password": "your password",
        "1d": "your 1d ESR rate prediction',
        "7d": "your 7d ESR rate prediction',
        "30d": "your 30d ESR rate prediction',
    }
)
```


# Integration Proposal

This page lists the options to incorporate TESR into your product, e.g., lending/borrowing protocols.

A lack of standardised benchmark rates in DeFi, having pioneered the decentralised consensus mechanism, which collectively has around $100B locked, has resulted in [disorganised rates](https://www.treehouse.finance/blog/branching-out-3) in financial products across the ecosystem. The [TESR](/protocol/tesr/treehouse-ethereum-staking-rate-tesr) aims to be one such benchmark available for reference.

One of the major market segments, lending/borrowing, seems to have consciously ended up using Lido's staking rate as one such benchmark. [Aave](https://governance.aave.com/t/arfc-weth-wsteth-borrow-rate-updates/19550) and [Spark](https://forum.sky.money/t/14-nov-2024-proposed-changes-to-spark-for-upcoming-spell/25466/2#p-99720-mainnet-adjust-sparklend-eth-interest-rate-model-4), among others, have advertently defined the WETH interest rates for their pools based on the Ethereum staking rate, or rather certain bps below it to encourage borrowing. However, the Lido rate they use only represents a portion of the validators' earnings on the network. As TESR reflects the average earnings of the entire network, we believe it could be a new standard that protocols can adopt when defining their interest rate models.

Almost all interest rate models in DeFi, to this day, are in one form or another, based on the interest rate strategy pioneered by Aave, which defines a linear curve with a kink at the end to optimise the utilisation around a predefined number (\~90% in most cases). TESR can be used to set the slope for the first part of the curve, reflecting the real-time adoption of network rate to define the interest rates.

{% hint style="info" %}
TESR is calculated at epoch level (every 32 slots of beacon chain, i.e., \~6.4 minutes) and aggregated at EOD to publish the daily value. An update is technically possible at this higher frequency, if required, for a more real-time reflection of current market conditions instead of the retrospective daily. This is currently being worked on by the team and planned to release in early part of Q2 2025.
{% endhint %}

## Options

{% content-ref url="/pages/QLy5OYJGKMLPnJsE4T8U" %}
[Async Operation](/protocol/tesr/integration-proposal/async-operation)
{% endcontent-ref %}

{% content-ref url="/pages/0X5sDCWr8wzfmNEGm4Le" %}
[Atomic Callback](/protocol/tesr/integration-proposal/atomic-callback)
{% endcontent-ref %}


# Async Operation

Use for off-chain processes.

TESR is published daily and is accessible through [API](/protocol/dor-operated-by-treehouse/staking-rate-tesr/get-published-rates/api) and [smart contract](/protocol/dor-operated-by-treehouse/staking-rate-tesr/get-published-rates/smart-contract) queries, both of which are publicly available. A protocol can use these methods to get the latest rate asynchronously. These are called *pull* requests, since it requires the protocol's off-chain operation or process to query it and the onus to fetch the latest rates is on them.

## Using API

Simply make an `HTTPS` `GET` request to the [latest endpoint](/protocol/dor-operated-by-treehouse/staking-rate-tesr/get-published-rates/api#latest) and get the value.

## Using Smart Contract

Use one of widely available open-source web3 libraries and a blockchain node (freely available as well) to call the `getLatestESR` smart contract method. The contract addresses can be found [here](/protocol/dor-operated-by-treehouse/staking-rate-tesr/get-published-rates/smart-contract#spot-tesr). Use the `decimals` method to know the number of decimals points to apply to the value.

{% hint style="info" %}
An event, `ESRUpdate` ([example transaction](https://sepolia.etherscan.io/tx/0x8c2d72f51b77985ae42fbeb25feb3e935c8f4d824e6901244b9031e77c83b22e#eventlog)), is emitted whenever the latest TESR value is published on-chain. The event log contains the published value (without the decimals). Optionally, an event listener can be used to detect this event and any of the above pull methods can be used to query the latest value.
{% endhint %}


# Atomic Callback

Use for on-chain processes.

For a more robust and direct on-chain update of TESR value on the destination smart contract, which adopts it as a reference, an atomic operation is recommended using a [Chainlink-like architecture](https://docs.chain.link/architecture-overview/architecture-overview)-based request model. Here, publisher will collect all the requests from protocols that want the latest TESR and, later, execute a series of on-chain function calls to update the destination smart contract with new value, when it becomes available. This whole *push* model process is atomic, because of the nature of blockchain, and requires less maintenance from the end user.

{% hint style="info" %}
This is not yet implemented and release schedule is TBD.
{% endhint %}