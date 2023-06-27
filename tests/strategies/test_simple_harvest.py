from brownie import chain, Contract, interface
from utils import harvest_strategy
import pytest

# test the our strategy's ability to deposit, harvest, and withdraw, with different optimal deposit tokens if we have them
def test_simple_harvest(
    gov,
    token,
    vault,
    whale,
    strategy,
    amount,
    sleep_time,
    is_slippery,
    no_profit,
    profit_whale,
    profit_amount,
    target,
    use_yswaps,
    is_gmx,
    gauge,
    to_sweep,
):
    ## deposit to the vault after approving
    starting_whale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    newWhale = token.balanceOf(whale)

    # harvest, store asset amount
    (profit, loss, extra) = harvest_strategy(
        is_gmx,
        strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        target,
    )
    old_assets = vault.totalAssets()
    assert old_assets > 0
    assert strategy.estimatedTotalAssets() > 0

    # simulate profits
    chain.sleep(sleep_time)

    # harvest, store new asset amount
    (profit, loss, extra) = harvest_strategy(
        is_gmx,
        strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        target,
    )
    print("Profit:", profit / 1e18)
    # ~0.523774613% left in strategy after harvest

    # check how much velo is claimable to know how effective our selling is
    print("\nClaimable after first harvest:", strategy.claimableRewards() / 1e18)
    print("Reward per Token Paid", gauge.userRewardPerTokenPaid(strategy) / 1e18)
    print("Rewards", gauge.rewards(strategy) / 1e18)
    print("Strategy velo balance:", to_sweep.balanceOf(strategy) / 1e18)

    # check the balance of each of our tokens, should be close to zero
    token0 = interface.IERC20(strategy.poolToken0())
    token1 = interface.IERC20(strategy.poolToken1())
    token0_balance = token0.balanceOf(strategy) / 1e6
    token1_balance = token1.balanceOf(strategy) / 1e18
    print("\n🧐 Token 0 Balance after Harvest (USDC):", token0_balance, token0.symbol())
    print("🧐 Token 1 Balance after Harvest (BLU):", token1_balance, token1.symbol())
    efficiency = (token0.balanceOf(strategy) * 100) / (
        gauge.userRewardPerTokenPaid(strategy) * 0.09 / 1e12
    )
    print("Volatile Vault swap leftover:", "{:,.4f}%".format(efficiency))

    # record this here so it isn't affected if we donate via ySwaps
    strategy_assets = strategy.estimatedTotalAssets()

    # harvest again so the strategy reports the profit
    if use_yswaps or is_gmx:
        print("Using ySwaps for harvests")
        (profit, loss, extra) = harvest_strategy(
            is_gmx,
            strategy,
            token,
            gov,
            profit_whale,
            profit_amount,
            target,
        )

    # evaluate our current total assets
    new_assets = vault.totalAssets()

    # confirm we made money, or at least that we have about the same
    if no_profit:
        assert pytest.approx(new_assets, rel=RELATIVE_APPROX) == old_assets
    else:
        new_assets > old_assets

    # simulate five days of waiting for share price to bump back up
    chain.sleep(86400 * 5)
    chain.mine(1)

    # Display estimated APR
    print(
        "\nEstimated APR: ",
        "{:.2%}".format(
            ((new_assets - old_assets) * (365 * 86400 / sleep_time)) / (strategy_assets)
        ),
    )

    # withdraw and confirm we made money, or at least that we have about the same
    vault.withdraw({"from": whale})
    if no_profit:
        assert (
            pytest.approx(token.balanceOf(whale), rel=RELATIVE_APPROX) == starting_whale
        )
    else:
        assert token.balanceOf(whale) > starting_whale
