import brownie
from brownie import chain, interface, accounts
import pytest
from utils import harvest_strategy


# this test makes sure we can use keepVELO
def test_keep(
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
    to_sweep,  # this is VELO
):
    ## deposit to the vault after approving
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})

    # harvest as-is before we have yield to hit all parts of our if statement
    strategy.setVoter(gov, {"from": gov})
    strategy.setLocalKeepVelo(1000, {"from": gov})

    # harvest our funds in
    (profit, loss, extra) = harvest_strategy(
        use_yswaps,
        strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        target,
    )

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)

    # normal operation
    treasury_before = to_sweep.balanceOf(strategy.veloVoter())

    (profit, loss, extra) = harvest_strategy(
        use_yswaps,
        strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        target,
    )

    treasury_after = to_sweep.balanceOf(strategy.veloVoter())
    if not no_profit:
        assert treasury_after > treasury_before

    # keepCRV off only
    strategy.setLocalKeepVelo(0, {"from": gov})
    treasury_before = to_sweep.balanceOf(strategy.veloVoter())

    (profit, loss, extra) = harvest_strategy(
        use_yswaps,
        strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        target,
    )

    treasury_after = to_sweep.balanceOf(strategy.veloVoter())
    assert treasury_after == treasury_before

    strategy.setLocalKeepVelo(1000, {"from": gov})
    strategy.setVoter(gov, {"from": gov})

    (profit, loss, extra) = harvest_strategy(
        use_yswaps,
        strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        target,
    )

    # both off
    strategy.setLocalKeepVelo(0, {"from": gov})

    (profit, loss, extra) = harvest_strategy(
        use_yswaps,
        strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        target,
    )


# this tests using a vault that is a stable pool (USDC/DOLA)
# normal simple harvest test, but just use a different vault/pool
def test_stable_vault(
    gov,
    stable_token,
    stable_vault,
    stable_strategy,
    stable_whale,
    stable_amount,
    sleep_time,
    no_profit,
    stable_profit_whale,
    stable_profit_amount,
    target,
    use_yswaps,
    is_gmx,
    stable_gauge,
    to_sweep,
):
    print("We made it into the test!!!!")
    whale = stable_whale
    token = stable_token
    vault = stable_vault
    strategy = stable_strategy
    amount = stable_amount
    profit_whale = stable_profit_whale
    profit_amount = stable_profit_amount
    gauge = stable_gauge

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

    # print our routes
    print("Token0 Route:", strategy.veloRouteToToken0())
    print("Token1 Route:", strategy.veloRouteToToken1())

    # simulate profits
    chain.sleep(sleep_time)

    # check how much velo is claimable to know how effective our selling is
    earned_velo = strategy.claimableRewards() / 1e18

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
    # get ~0.0801384153% left in strategy after harvest

    # check how much velo is claimable to know how effective our selling is
    print("\nEarned after first harvest:", strategy.claimableRewards() / 1e18)
    print("Reward per Token Paid", gauge.userRewardPerTokenPaid(strategy) / 1e18)
    print("Rewards", gauge.rewards(strategy) / 1e18)
    print("Strategy velo balance:", to_sweep.balanceOf(strategy) / 1e18)

    # check the balance of each of our tokens, should be close to zero
    token0 = interface.IERC20(strategy.poolToken0())
    token1 = interface.IERC20(strategy.poolToken1())
    token0_balance = token0.balanceOf(strategy) / 1e6
    token1_balance = token1.balanceOf(strategy) / 1e18
    print("\n🧐 Token 0 Balance after Harvest:", token0_balance, token0.symbol())
    print("🧐 Token 1 Balance after Harvest:", token1_balance, token1.symbol())
    efficiency = (token0.balanceOf(strategy) * 100) / (
        gauge.userRewardPerTokenPaid(strategy) * 0.09 / 1e12
    )
    print("Stable Vault swap leftover:", "{:,.4f}%".format(efficiency))

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


# this tests using a vault that is a stable pool (USDC/DOLA)
# normal simple harvest test, but just use a different vault/pool
def test_stable_vault_donation(
    gov,
    stable_token,
    stable_vault,
    stable_strategy,
    stable_whale,
    stable_amount,
    sleep_time,
    no_profit,
    stable_profit_whale,
    stable_profit_amount,
    target,
    use_yswaps,
    is_gmx,
    stable_gauge,
    to_sweep,
):
    print("We made it into the test!!!!")
    whale = stable_whale
    token = stable_token
    vault = stable_vault
    strategy = stable_strategy
    amount = stable_amount
    profit_whale = stable_profit_whale
    profit_amount = stable_profit_amount
    gauge = stable_gauge

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

    # print our routes
    print("Token0 Route:", strategy.veloRouteToToken0())
    print("Token1 Route:", strategy.veloRouteToToken1())

    # simulate profits
    chain.sleep(sleep_time)

    # check how much velo is claimable to know how effective our selling is
    earned_velo = strategy.claimableRewards() / 1e18

    # add in some extra USDC to make sure this won't revert swaps
    usdc = interface.IERC20("0x7F5c764cBc14f9669B88837ca1490cCa17c31607")
    usdc_whale = accounts.at("0x85149247691df622eaF1a8Bd0CaFd40BC45154a9", force=True)
    usdc.transfer(strategy, 1_000e6, {"from": usdc_whale})

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
    # get ~0.0801384153% left in strategy after harvest

    # check how much velo is claimable to know how effective our selling is
    print("\nEarned after first harvest:", strategy.claimableRewards() / 1e18)
    print("Reward per Token Paid", gauge.userRewardPerTokenPaid(strategy) / 1e18)
    print("Rewards", gauge.rewards(strategy) / 1e18)
    print("Strategy velo balance:", to_sweep.balanceOf(strategy) / 1e18)

    # check the balance of each of our tokens, should be close to zero
    token0 = interface.IERC20(strategy.poolToken0())
    token1 = interface.IERC20(strategy.poolToken1())
    token0_balance = token0.balanceOf(strategy) / 1e6
    token1_balance = token1.balanceOf(strategy) / 1e18
    print("\n🧐 Token 0 Balance after Harvest:", token0_balance, token0.symbol())
    print("🧐 Token 1 Balance after Harvest:", token1_balance, token1.symbol())
    efficiency = (token0.balanceOf(strategy) * 100) / (
        gauge.userRewardPerTokenPaid(strategy) * 0.09 / 1e12
    )
    print("Stable Vault swap leftover:", "{:,.4f}%".format(efficiency))

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


# this tests using a vault that is a velo pool
# normal simple harvest test, but just use a different vault/pool
def test_velo_vault(
    gov,
    velo_token,
    velo_vault,
    velo_strategy,
    velo_whale,
    velo_amount,
    sleep_time,
    no_profit,
    velo_profit_whale,
    velo_profit_amount,
    target,
    use_yswaps,
    is_gmx,
    velo_gauge,
    to_sweep,
):
    print("We made it into the test!!!!")
    whale = velo_whale
    token = velo_token
    vault = velo_vault
    strategy = velo_strategy
    amount = velo_amount
    profit_whale = velo_profit_whale
    profit_amount = velo_profit_amount
    gauge = velo_gauge

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
    # ~ 0.1485977028% left in strategy after harvest

    # check how much velo is claimable to know how effective our selling is
    print("\nEarned after first harvest:", strategy.claimableRewards() / 1e18)
    print("Reward per Token Paid", gauge.userRewardPerTokenPaid(strategy) / 1e18)
    print("Rewards", gauge.rewards(strategy) / 1e18)
    print("Strategy velo balance:", to_sweep.balanceOf(strategy) / 1e18)

    # check the balance of each of our tokens, should be close to zero
    token0 = interface.IERC20(strategy.poolToken0())
    token1 = interface.IERC20(strategy.poolToken1())
    token0_balance = token0.balanceOf(strategy) / 1e6
    token1_balance = token1.balanceOf(strategy) / 1e18
    print("\n🧐 Token 0 Balance after Harvest:", token0_balance, token0.symbol())
    print("🧐 Token 1 Balance after Harvest:", token1_balance, token1.symbol())
    efficiency = (token1_balance * 100) / (
        gauge.userRewardPerTokenPaid(strategy) / 1e18
    )
    print("VELO Vault swap leftover:", "{:,.4f}%".format(efficiency))

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
