# Introduction

In traditional finance, reference rates serve as benchmarks for various financial products, helping to establish standards and facilitate efficient pricing. Decentralized Offered Rates (*DOR*) are reference rates derived from the Treehouse Protocol, a consensus mechanism incentivizing an economy of stakeholders to provide accurate data and forecasts.&#x20;

The Treehouse Protocol is designed to support deterministic reference rates. This means that the final rate output derived from consensus must be grounded in objective data that can be validated, such as trading data or index formulas. Such objectivity safeguards *DOR* from manipulation or influence by external factors, unlike subjective reference rates that rely on inputs based on unverifiable opinions. For more information on the various types of reference rates, refer to the Reference Rate Models and Reference Rate Properties sections in the [appendix](/protocol/dor/appendix).

**Challenges To Existing Reference Rates**

In the USD market, the London InterBank Offered Rate (LIBOR) was the benchmark used by the majority of USD financial products from the 1980s until its replacement by the Secured Overnight Financing Rate (SOFR) in 2023. The shift was prompted by the revelation of collusion among bankers at major financial institutions, who manipulated their rate submissions to favor their trading activities.&#x20;

While the new SOFR methodology offers advantages in terms of data authenticity, being calculated from trillions of dollars worth of overnight repo transactions on a daily basis, it presents its own set of challenges. Unlike LIBOR, SOFR lacks a term structure, as it is reported solely as a backward-looking overnight rate. Consequently, longer tenor products requiring reference rates must rely on futures contract data such as the [Term SOFR Reference Rates](https://www.cmegroup.com/market-data/files/cme-term-sofr-reference-rates-benchmark-methodology.pdf) published by the CME Group. This dependency on a single publicly listed entity introduces significant centralization risks and represents a single point of failure for the entire SOFR ecosystem.&#x20;


# Key Design Principles

The Treehouse Protocol is built on several design principles aimed at addressing the shortcomings of traditional finance reference rates and ensuring the effectiveness and reliability of its consensus mechanism. These principles include:

**Accuracy**

Accuracy is paramount in the design of the Treehouse Protocol. To achieve this, the protocol employs Game Theory principles. In the rate consensus process, participants, known as "Panelists," are required to stake some of their capital as collateral. This collateral acts as a deterrent against malicious actions, as any attempt to undermine the system results in penalties. Conversely, participants who contribute to the rate consensus with integrity are duly rewarded. Token emissions and referencing fees serve as incentives for good behavior, tying potential earnings directly to the accuracy of predictions. This multi-tiered reward system encourages participants to build a strong reputation over time and to provide their best predictions.

**Decentralization**

The Treehouse Protocol aims to promote decentralization in the rate-fixing process. This decentralization is facilitated by allowing anyone with subject matter expertise to build their own *DOR* ecosystem or to predict the relevant rate defined by the Operator, provided they adhere to the outlined incentive and penalty framework. Open access to *DOR* also ensures that knowledge and insight are valued over centralized authority, fostering a diverse range of perspectives in the consensus process. Additionally, the computation of the rate consensus is publicly accessible on the blockchain, offering transparency for all stakeholders to validate the protocol's calculations. Participants, known as “Delegators” can further decentralize the ecosystem by entrusting their stake to knowledgeable Panelists, who are incentivized to act in their best interest. &#x20;

**Agnosticism**

The Treehouse Protocol introduces a generalized framework to the rate consensus process, making it applicable to all objective reference rates. This versatility extends the use of *DOR* beyond conventional rates within the cryptocurrency ecosystem, such as Ethereum staking rates, to include a wide array of other financial products. These may include liquidity provider (LP) yield for specific pools or real-world asset (RWA) related rates like a mortgage rate index. This broad scope of application opens up numerous possibilities for leveraging the Treehouse Protocol in diverse scenarios, enhancing its utility across various sectors.


# Stakeholders

Treehouse is committed to establishing a system that ensures appropriate power distribution and incorporates adequate checks and balances. The stakeholder concept draws inspiration from both democratic societies and corporate governance structures, dividing authority into different bodies.\
\
For a quick definition of the different stakeholders check [Key Terms](/protocol/overview/key-terms).


# Checks & Balances

In the Treehouse ecosystem, the integrity of the system is maintained through a network of checks and balances among its five categories of participants, each relying on the others to safeguard their best financial interests.

* **Operator**: Operators initiate and administer the *DOR* system, incentivized by Referencers who contribute revenue through querying fees. They continuously improve and maintain the *DOR* system and recruit top-quality Panelists and Delegators. Despite their role as administrators, Operators depend on the subject matter expertise of Panelists to ensure the accuracy and decentralization of the consensus rate.
* **Panelists**: Panelists rely on Operators and Referencers to provide financial incentives for their work on rate predictions. They earn from a reward pool set aside by the Operator and receive a portion of the query fees paid by Referencers. Delegators also play a crucial role in ensuring the quality of Panelists' work. Panelists' track records for rate predictions are publicly available, serving as a key metric for attracting delegations to boost the yield of Panelists' rewards during each observation period.
* **Delegators**: Delegators rely on their share of the Operator’s reward pool and querying fees from Referencers for financial incentives. Unlike Panelists, they do not possess the subject matter expertise required for rate consensus and instead rely on the delegated Panelists to participate in the process and earn rewards. At the same time, the *tAssets* delegated by Delegators extend cryptoeconomic security to DOR.&#x20;
* **Referencers**: Referencers depend on Panelists to provide accurate rate predictions, ensuring reliable data for research and pricing of financial products. They also rely on Operators to maintain the *DOR*, who provide ongoing incentives to Panelists and Delegators. Referencers also depend on demand from End Users to earn fee revenues on each transaction.
* **End Users**: End Users of *DOR* rely on Referencers to offer financial products for trading and speculation. They depend on Panelists to provide accurate predictions, minimizing losses resulting from the basis risk between *DOR* rates and realized rates. Additionally, End Users rely on Operators to maintain the *DOR* system, ensuring a seamless trading experience, and pay a portion of their trading fee to keep this system running smoothly.&#x20;

<figure><img src="/files/OQaI90tvcEh7JRoDegPc" alt=""><figcaption></figcaption></figure>


# Consensus Mechanism

Operators define the rate and set parameters for Panelists to forecast. The Treehouse Protocol then aggregates independent data points provided by the Panelists and derives the final consensus rate using the following mechanisms:

1. **Outlier Value (OV) Removal**: Predictions are organized in descending order, and a designated percentage of the largest and smallest values, known as “Outlier Values (OV)” predictions, are removed. This step prevents any outsized skewing of the final rate consensus.
2. **Random Sampling**: The remaining data submissions are randomly sampled to create the final group of submissions for the consensus calculation. This step is enforced only when the number of Panelists for the specific *DOR* reaches a critical threshold defined by the Operator, ensuring that the sampled population remains statistically representative of the total population.
3. **Consensus Mean**: The mean of the remaining sampled submissions is used to determine the final consensus rate on the *DOR*. This process effectively acts as a trimmed mean from the original submissions, providing a statistically reliable metric for Referencers.
4. **Out-of-Range (OR) Setting**: Throughout the observation period, the Treehouse Protocol records the realized rate for each period, which is then used to compute the "Out-of-Range (OR)" boundary, calculated based on the standard deviation of the panelist's predictions and the actual realized rate during the period.
5. **Payout and Penalty**: At the end of the observation period, Panelists and Delegators whose original submission falls outside of the OR boundary will be penalized according to the protocol’s [Slashing Mechanism](/protocol/dor/slashing-mechanism). Meanwhile, the rest of the Panelists and Delegators are rewarded as per the protocol’s [Payout Mechanism](/protocol/dor/payout-mechanism).

<figure><img src="/files/wBaIcAniaANg94AGI1uK" alt=""><figcaption></figcaption></figure>


# Payout Mechanism

The *DOR* ecosystem is designed to provide monetary incentives to participants who contribute positively to the system's operations. At the outset, the *DOR* operator establishes a reward pool to compensate Panelists and Delegators. Throughout each observation period, Panelists make predictions on reference rates, and those who accurately forecast the rates, along with their respective Delegators, receive payouts from the rewards pool.&#x20;

Furthermore, the Operator may specify the method of payouts, which can either be in the form of direct native tokens or escrowed tokens. Escrowed tokens follow a vesting schedule, allowing for gradual release over time. Participants may have the option for early withdrawal of escrowed tokens, although this may incur penalties as determined by the Operator.


# Panelist Pool

During each observation period, rewards are allocated to Panelists whose predictions fall within the OR boundaries. This range, determined by the Operator in terms of standard deviations from the realized rate during the observation period, ensures that Panelists who accurately predict the rate are duly rewarded. Panelists whose predictions fall outside the OR boundaries will not receive any rewards for that observation period and may be subject to slashing according to the criteria outlined in the [Slashing Mechanism](/protocol/dor/slashing-mechanism) section.

Specifically, the allocation of rewards per submission period is inversely proportional to the absolute difference between each Panelist's prediction and the realized rate. Panelists whose predictions closely match the realized rates receive a larger share of token emissions proportional to their accuracy.


# Delegator Pool

Delegators within the Treehouse ecosystem earn rewards contingent on the performance of the Panelists they have delegated to. When the delegated Panelists receive rewards for a particular submission period, Delegators are entitled to a portion of the Delegator Pool commensurate with the percentage of their delegated Panelists' share in the Panelist Pool.

Subsequently, the rewards distributed to each Delegator is proportional to their percentage stake in the total amount delegated to that Panelist, net of any applicable commissions.


# Payout Example

Consider a scenario where a *DOR* set by an Operator involves five Panelists and 15 Delegators, with the native token $NT being the reward in each observation period.&#x20;

Below is an example of the payout, assuming three Panelists are rewarded for their reporting accuracy, with a 30%/70% split between the Panelist and Delegator Reward Pool.

<figure><img src="/files/l11C98AlZsTi1Wja0KJ6" alt=""><figcaption></figcaption></figure>


# Payout in DORs with Multiple Tenors

If the Operator requires Panelists to submit forecasts for different tenors simultaneously, the Panelist Reward Pool will be divided among the various forecast groups to incentivize predictions for each tenor separately. The reward distribution is determined by the Operator, which may use set percentages or specific formulas to allocate rewards.&#x20;

As a general guideline, Operators are encouraged to allocate a higher proportion of rewards to longer-tenor predictions, reflecting the greater uncertainty associated with these forecasts compared to shorter-tenor ones. For example, an Operator could apply a square root time-weighting method, where the reward allocation for each forecast is proportional to the square root of its tenor.

In practice, if an Operator requires Panelists to predict DOR values for tenors of 1-day, 7-day, 14-day, and 30-day on a daily basis, the reward allocation could look as follows:

<figure><img src="https://lh7-rt.googleusercontent.com/docsz/AD_4nXfSPbhkr8VINRuVyVkFLcaW6D51HGzYw9ZLSFLrvzt6j8Di-CuK8dBw5qHLKsh9VJ_F09rf3VgzaeFiR15QGyHxB7o63WwgqpgpyKLeAsHBel3bW3jRDQhZoFsQ56Dc_C8cdb0G_w?key=UnNNG5z4pnhLNIpixfKbdg" alt=""><figcaption></figcaption></figure>

In this specific example, approximately **7.77%** of the rewards each day would be directed to all Panelists who submitted predictions for the 1-day tenor, **20.57%** for those who submitted predictions for the 7-day tenor, and so on.


# Slashing Mechanism

The slashing mechanism is designed to discourage collusion or malicious predictions by Panelists. Predictions that deviate significantly from the final fixing at the end of the observation period may incur penalties.

In a slashing event, Panelists and their respective Delegators are at risk of losing a portion or all of their stake if their predictions fall outside of the defined OR boundaries at the end of the observation period. When a Panelist is subject to slashing, their Delegators also face a corresponding percentage reduction in their delegated stake.

## Example

Consider a scenario where a group of Panelists predicts a specific rate over a future 7-day period, with the Operator setting three standard deviations as the benchmark for slashing. Here's how different situations may unfold:

* In-Range: Let’s say a Panelist submits a prediction of 3.7% for the period and the realized rate is 3.5% while the standard deviation of panelist predictions is 0.1%. Then, the OR boundary can be computed as (the realized rate +/- three standard deviations), which is 3.2% and 3.8%. In this scenario, no slashing will occur as the prediction is within the acceptable range.
* Out-of-Range: However, if a Panelist predicts 4.0% for the period, in the same scenario, the Panelist’s prediction falls outside the three standard deviation boundary. In such a case, slashing of the Panelist’s stake, as well as their delegated stake, will be enforced according to the prescribed slashing schedule.

Safety Boundary: A safety boundary may be implemented to prevent panelists from being slashed when all submissions are highly accurate. For example, consider a case where the realized rate is 3.5% and the standard deviation of Panelist prediction is 0.02%, which is quite small. The OR boundary would be at 3.44% and 3.56%. If a safety boundary is drawn at the realized rate +/- 0.2%, (Range between 3.3% and 3.7%), Panelists whose submissions are within this range would not be penalized, even though some of their predictions fall outside the OR boundary.


# Slashing Formula

In general, the cumulative amount slashed increases exponentially in the event of consecutive OR predictions made by a Panelist. To account for genuine differences in opinion and prevent penalizing Panelists for unintentional errors, a forgiveness clause can be incorporated into the mechanism. This clause also prevents slashing due to accidental OR predictions and allows Panelists to adjust their model parameters to better align with the evolving market landscape.

The general formula for calculating the cumulative slash at the end of each slashing event is as follows:

$$
f(k) = \left(\frac{max(k, n)-n}{N-n}\right)^2 \quad \text{where} \quad 0 < n \leq N
$$

*where,*

* **f** is a function of the cumulative slashes given the number of consecutive slashing events
* **k** is the number of consecutive OR submissions by the Panelist
* **N** is the number of consecutive slashing OR submissions for the Panelist to be fully slashed
* **n** is the number of consecutive OR submissions that will be forgiven before slashing is enforced

Based on this formula, an example slashing schedule will commence as follows if n = 1 and N = 8, meaning that a Panelist is forgiven once, and the full amount staked will be slashed at the 8th consecutive OR:

<figure><img src="/files/EojNyEHFFEg5pygWBTvo" alt=""><figcaption></figcaption></figure>


# Distribution of Slashed Tokens

After a slashing event occurs within the Treehouse Protocol, a structured distribution process is initiated to ensure fairness and incentivize accuracy among Panelists. The following parameters regarding the distribution of slashed tokens can be defined by the Operator:

* **Token Burn**: A percentage of the slashed tokens can be permanently removed from circulation through a burn mechanism.
* **Redistribution to Best Performing Panelist**: Similar to the [Payout Mechanism](/protocol/dor/payout-mechanism), the best predictors can be defined by the Operators as those who provide the predictions within certain standard deviations of the realized rate. The redistribution will be made in the form of escrowed tokens. The exact amount of distributions is inversely proportional to the absolute difference between their submitted predictions and the realized rate. This incentivizes Panelists to perform their best efforts to align with the market consensus which, in turn, promotes a competitive and accurate prediction system. In instances where multiple Panelists make the same predictions, the redistributed tokens are divided equally among them. Tokens will also be redistributed to Delegators who have entrusted their stake to the rewarded Panelists, mirroring the mechanisms described in the [Payout Mechanisms](/protocol/dor/payout-mechanism).


# Slashing in DORs with Multiple Tenors

Similar to the [Payout in DORs with Multiple Tenors](/protocol/dor/payout-mechanism/payout-in-dors-with-multiple-tenors), Operators are required to specify a breakdown of the Panelists’ stake that is slashable for each prediction tenor, This breakdown can be defined using percentages or determined through specific formulas.

Unlike payout mechanisms, Operators are generally encouraged to slash a **smaller** proportion of the Panelists’ stake for longer tenor predictions, acknowledging the greater difficulty and uncertainty of forecasts over extended periods. For instance, an Operator could use a 1/square root time-weighting method to determine the slashable portion of the Panelists’ total stake for each tenor.

If an Operator requires Panelists to predict DOR values for tenors of 1-day, 7-day, 14-day, and 30-day on a daily basis, the slashable portions might be allocated as follows:

<figure><img src="https://lh7-rt.googleusercontent.com/docsz/AD_4nXewbqe7ceC7J64aIN7LrZjjHxY7m6Ngpax9FszSPuZ66vdVeybiBbiUF6swxATwyqh2E-AljMTh2MA0Pm3XTHh3PxFk9-rM2KPwg1q_mULKN-sNG-Ziw_WfUraX4ofRXftlsy8P5g?key=UnNNG5z4pnhLNIpixfKbdg" alt=""><figcaption></figcaption></figure>

This means if a Panelist’s prediction for the 1-day tenor falls outside the Operator-defined range (OR bands) after the rate is realized, up to 54.71% of their stake may be slashable. The actual slashed amount will follow the Operator’s slashing schedule. For instance, if a 10% slashing rate is applied to the 1-day tenor, the effective slashed amount would be **10% x 54.71% = 5.47%** of the Panelist's total stake.


# Exceptional Cases

In scenarios where the realized rate experiences significant volatility, the Operator may define parameters to determine which Panelists and Delegators are rewarded or penalized. For example, if none of the Panelist predictions fall within the OR boundaries, the Operator may exempt a group of Panelists with predictions closest to the realized rate from slashing. These panelists would receive the full consensus reward and any redistributed tokens, as they are deemed the most accurate predictors for that observation period.

Here's a graphical representation of this scenario:

<figure><img src="/files/KRHPlftJ3L4KqTTIfYR0" alt=""><figcaption></figcaption></figure>


# Glossary

| **Term**                             | **Definition**                                                                                                                                                                                                                                                               |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Consensus Payout Token               | The token used by the Operator to reward Panelists and Delegators at the conclusion of an observation period.                                                                                                                                                                |
| Early Withdrawal Penalty             | The percentage of tokens that a user forfeits or must return if they choose to claim their tokens before the completion of the full vesting period.                                                                                                                          |
| Exceptional Case                     | A scenario where the OR boundary does not intersect with any panelists' predictions during an observation period. For more information, read Exception Case.                                                                                                                 |
| Forgiveness Clause                   | A provision that grants leniency or exemption from penalties for a specified number of consecutive instances of out-of-range (OR) predictions that a user can make before facing punitive actions.                                                                           |
| Full Slash                           | The number of consecutive slashing events for the Panelist to be fully slashed.                                                                                                                                                                                              |
| Linear Vesting                       | A distribution mechanism where token rewards are released gradually over a specified period in equal increments. Recipients receive a consistent amount of tokens at regular intervals until the total reward is fully distributed.                                          |
| Out-of-Range (OR)                    | Refer to forecasts that fall outside the Operator's acceptable range at the conclusion of an observation period. The OR Boundaries serve as thresholds used by the protocol to determine rewards and penalties for Panelists based on the accuracy of their predictions.     |
| Outlier Values (OV)                  | Values that significantly deviate from other Panelists' predictions with the potential to skew or distort the overall data, defined by the Operator. These outliers are excluded from the consensus calculation to ensure the accuracy and reliability of the derived rates. |
| Panelist/Delegator Reward Pool Split | The distribution ratio between Panelists and Delegators for each observation period, determining how rewards from the reward pool are divided between these two groups.                                                                                                      |
| Query Fee                            | Refers to the fees paid by the Referencer to the Operator for accessing or referencing the DOR, typically determined by the Operator during the initialization stage of the DOR.                                                                                             |
| Realized Rate Compounding            | Refers to the process of continuously reinvesting or accumulating realized rates at the end of each day.                                                                                                                                                                     |
| Slashing                             | The punitive action taken where a user's collateral or staked assets are confiscated or reduced as a penalty for engaging in undesirable or malicious behavior.                                                                                                              |
| Vesting Cliff                        | The initial period after which token rewards begin to accrue but are not immediately available for withdrawal or use. During this period, the tokens accumulate but remain locked, and they are typically released in full once the cliff period ends.                       |


# Applications

Treehouse will serve as the first Operator, establishing the Ethereum Staking Rate (ESR) in the near future.

## Ethereum Staking Rate (ESR)

The Ethereum Staking Rate (*ESR*) is a broad measure of the native “risk-free” rate of the Ethereum ecosystem. By aligning the calculations of *ESR* with Ethereum's staking dynamics, Treehouse ensures a transparent and tamper-resistant framework for reaching consensus on ETH rates.

Through the Treehouse Protocol, an *ESR* curve can be extrapolated, offering valuable insights into Ethereum's staking dynamics. This curve can serve as a basis for developing innovative financial products such as Ethereum Staking Rate Futures or Ethereum Staking Rate Swaps. These products cater to the diverse needs of investors and staking rate hedgers within the Ethereum ecosystem, providing them with effective tools for managing risk and optimizing return.


# Appendix

## Reference Rate Models

There are various models to determine benchmark rates. Here are some of the more common models used in traditional finance:\
\
**Interbank Offered Rate (IBOR)**: IBOR rates represent the average interest rates at which banks are willing to lend to each other in the interbank market. Examples include: LIBOR (London Interbank Offered Rate) in the UK, EURIBOR (Euro Interbank Offered Rate) in the Eurozone, and TIBOR (Tokyo Interbank Offered Rate) in Japan.

**Treasury Yield Curve**: Treasury yield curves are widely used as reference rates in financial markets due to the perceived low risk associated with US Treasury securities, as they are backed by the full faith and credit of the government. For example, the United States 10-year Treasury bond.&#x20;

**Central Bank Policy Rate**: Central banks set policy rates to influence monetary policy and economic activity, and some financial products reference these rates. Examples include: the Federal Funds Rate in the US, the Bank Rate in the UK, and the European Central Bank's Main Refinancing Rate.&#x20;

**Overnight Reference Rates**: Countries may also adopt overnight reference rates based on transactions in the overnight lending markets. Examples include: SOFR (Secured Overnight Financing Rate) in the US, Sonia (Sterling Overnight Index Average) in the UK, and Eonia (Euro Overnight Index Average) in the Eurozone.

**Prime Rate**: The prime rate is the interest rate that commercial banks charge their most creditworthy customers. It serves as a benchmark for various loans, particularly consumer loans like mortgages and personal loans.

**Market-based Rates**: Some benchmark rates are derived from market transactions, such as swap rates, which are based on interest rate swaps. These rates provide a basis for pricing various financial instruments.&#x20;

**Customized Benchmark Rates**: In some cases, countries may develop customized benchmark rates tailored to their specific financial markets and needs. These rates could be based on a combination of the above factors.&#x20;

## Reference Rate Properties

Reference rates can be segmented based on various underlying properties. Here are some common ways to categorize them:

**Subjective vs Objective Inputs**: This classification refers to whether the reference rate is determined by subjective judgment or objective data. For example, interbank-offered rates (IBORs) like LIBOR were historically subjective, relying on banks' estimates of borrowing costs. In contrast, rates like SOFR and Sonia are objective, based on actual transactions in overnight lending markets.

**Backward vs Forward-Looking**: This classification distinguishes between rates that are backward-looking, meaning they are based on historical data, and rates that are forward-looking, meaning they are based on expectations for future interest rates. For example, LIBOR is a backward-looking rate, while some central bank policy rates, like the Federal Funds Rate, are forward-looking.

**Unsecured vs Secured**: This classification refers to whether the borrowing transactions underlying the reference rate are unsecured (without collateral) or secured (backed by collateral). For example, LIBOR and EURIBOR are unsecured rates, reflecting uncollateralized lending between banks, while rates like SOFR are secured, based on transactions in the secured overnight financing market.

**Spot vs Derivative**: This classification distinguishes between rates that are directly observed in the spot market and rates that are derived from financial instruments like derivatives. For example, overnight reference rates like SOFR and Sonia are spot rates, reflecting actual transactions in the overnight market. In contrast, swap rates are derivative rates, derived from the pricing of interest rate swaps.

**User Group Source**: This classification refers to the entities or groups from which the data used to calculate the reference rate is obtained. For example, central bank policy rates are determined by the government while prime rates data are sourced from consumer transactions.&#x20;