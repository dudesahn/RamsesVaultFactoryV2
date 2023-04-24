import pytest
import brownie
from brownie import interface, chain, accounts, ZERO_ADDRESS

# returns (profit, loss) of a harvest
def harvest_strategy(
    use_yswaps,
    strategy,
    token,
    gov,
    profit_whale,
    profit_amount,
    destination_strategy,
):

    # reset everything with a sleep and mine
    chain.sleep(1)
    chain.mine(1)

    # add in any custom logic needed here, for instance with router strategy (also reason we have a destination strategy).
    # also add in any custom logic needed to get raw reward assets to the strategy (like for liquity)

    ####### ADD LOGIC AS NEEDED FOR CLAIMING/SENDING REWARDS TO STRATEGY #######
    # usually this is automatic, but it may need to be externally triggered

    # claiming rewards should work just fine for this strategy, but we will earmark just in case
    try:
        booster = interface.IAuraBooster(strategy.depositContract())
        booster.earmarkRewards(strategy.pid(), {"from": gov})
    except:
        print("Not a convex strategy")

    # if we have no staked assets, and we are taking profit (when closing out a strategy) then we will need to ignore health check
    # we also may have profit and no assets in edge cases
    if strategy.stakedBalance() == 0:
        strategy.setDoHealthCheck(False, {"from": gov})
        print("\nTurned off health check!\n")

    # when in emergency exit we don't enter prepare return, so we should manually claim rewards when withdrawing
    if strategy.emergencyExit():
        strategy.setClaimRewards(True, {"from": gov})
    else:
        if strategy.claimRewards():
            strategy.setClaimRewards(False, {"from": gov})

    # we can use the tx for debugging if needed
    tx = strategy.harvest({"from": gov})
    profit = tx.events["Harvested"]["profit"] / (10 ** token.decimals())
    loss = tx.events["Harvested"]["loss"] / (10 ** token.decimals())

    # assert there are no loose funds in strategy after a harvest
    assert strategy.balanceOfWant() == 0

    # our trade handler takes action, sending out rewards tokens and sending back in profit
    if use_yswaps:
        trade_handler_action(strategy, token, gov, profit_whale, profit_amount)

    # reset everything with a sleep and mine
    chain.sleep(1)
    chain.mine(1)

    # return our profit, loss
    return (profit, loss)


# simulate the trade handler sweeping out assets and sending back profit
def trade_handler_action(
    strategy,
    token,
    gov,
    profit_whale,
    profit_amount,
):
    ####### ADD LOGIC AS NEEDED FOR SENDING REWARDS OUT AND PROFITS IN #######
    # get our tokens from our strategy
    crv = interface.IERC20(strategy.crv())
    cvx = interface.IERC20(strategy.convexToken())

    crvBalance = crv.balanceOf(strategy)
    if crvBalance > 0:
        crv.transfer(token, crvBalance, {"from": strategy})
        print("CRV rewards present")
        assert crv.balanceOf(strategy) == 0

    cvxBalance = cvx.balanceOf(strategy)
    if cvxBalance > 0:
        cvx.transfer(token, cvxBalance, {"from": strategy})
        print("CVX rewards present")
        assert cvx.balanceOf(strategy) == 0

    # send our profits back in
    if crvBalance > 0 or cvxBalance > 0:
        token.transfer(strategy, profit_amount, {"from": profit_whale})
        print("Rewards converted into profit and returned")
        assert strategy.balanceOfWant() > 0


# do a check on our strategy and vault of choice
def check_status(
    strategy,
    vault,
):
    # check our current status
    strategy_params = vault.strategies(strategy)
    vault_assets = vault.totalAssets()
    debt_outstanding = vault.debtOutstanding(strategy)
    credit_available = vault.creditAvailable(strategy)
    total_debt = vault.totalDebt()
    share_price = vault.pricePerShare()
    strategy_debt = strategy_params["totalDebt"]
    strategy_loss = strategy_params["totalLoss"]
    strategy_gain = strategy_params["totalGain"]
    strategy_debt_ratio = strategy_params["debtRatio"]
    strategy_assets = strategy.estimatedTotalAssets()

    # print our stuff
    print("Vault Assets:", vault_assets)
    print("Strategy Debt Outstanding:", debt_outstanding)
    print("Strategy Credit Available:", credit_available)
    print("Vault Total Debt:", total_debt)
    print("Vault Share Price:", share_price)
    print("Strategy Total Debt:", strategy_debt)
    print("Strategy Total Loss:", strategy_loss)
    print("Strategy Total Gain:", strategy_gain)
    print("Strategy Debt Ratio:", strategy_debt_ratio)
    print("Strategy Estimated Total Assets:", strategy_assets, "\n")

    # print simplified versions if we have something more than dust
    token = interface.IERC20(vault.token())
    if vault_assets > 10:
        print(
            "Decimal-Corrected Vault Assets:", vault_assets / (10 ** token.decimals())
        )
    if debt_outstanding > 10:
        print(
            "Decimal-Corrected Strategy Debt Outstanding:",
            debt_outstanding / (10 ** token.decimals()),
        )
    if credit_available > 10:
        print(
            "Decimal-Corrected Strategy Credit Available:",
            credit_available / (10 ** token.decimals()),
        )
    if total_debt > 10:
        print(
            "Decimal-Corrected Vault Total Debt:", total_debt / (10 ** token.decimals())
        )
    if share_price > 10:
        print("Decimal-Corrected Share Price:", share_price / (10 ** token.decimals()))
    if strategy_debt > 10:
        print(
            "Decimal-Corrected Strategy Total Debt:",
            strategy_debt / (10 ** token.decimals()),
        )
    if strategy_loss > 10:
        print(
            "Decimal-Corrected Strategy Total Loss:",
            strategy_loss / (10 ** token.decimals()),
        )
    if strategy_gain > 10:
        print(
            "Decimal-Corrected Strategy Total Gain:",
            strategy_gain / (10 ** token.decimals()),
        )
    if strategy_assets > 10:
        print(
            "Decimal-Corrected Strategy Total Assets:",
            strategy_assets / (10 ** token.decimals()),
        )

    return strategy_params
