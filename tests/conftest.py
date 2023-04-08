import pytest
from brownie import config, Contract, ZERO_ADDRESS, chain, interface, accounts
from eth_abi import encode_single
import requests


@pytest.fixture(scope="function", autouse=True)
def isolate(fn_isolation):
    pass


# set this for if we want to use tenderly or not; mostly helpful because with brownie.reverts fails in tenderly forks.
use_tenderly = False

# use this to set what chain we use. 1 for ETH, 250 for fantom, 10 optimism, 42161 arbitrum
chain_used = 1


################################################## TENDERLY DEBUGGING ##################################################

# change autouse to True if we want to use this fork to help debug tests
@pytest.fixture(scope="session", autouse=use_tenderly)
def tenderly_fork(web3, chain):
    fork_base_url = "https://simulate.yearn.network/fork"
    payload = {"network_id": str(chain.id)}
    resp = requests.post(fork_base_url, headers={}, json=payload)
    fork_id = resp.json()["simulation_fork"]["id"]
    fork_rpc_url = f"https://rpc.tenderly.co/fork/{fork_id}"
    print(fork_rpc_url)
    tenderly_provider = web3.HTTPProvider(fork_rpc_url, {"timeout": 600})
    web3.provider = tenderly_provider
    print(f"https://dashboard.tenderly.co/yearn/yearn-web/fork/{fork_id}")


################################################ UPDATE THINGS BELOW HERE ################################################

#################### FIXTURES BELOW NEED TO BE ADJUSTED FOR THIS REPO ####################

# for curve/balancer, we will pull this automatically, so comment this out here (token below in unique fixtures section)
# @pytest.fixture(scope="session")
# def token():
#     token_address = "0x6DEA81C8171D0bA574754EF6F8b412F2Ed88c54D"  # this should be the address of the ERC-20 used by the strategy/vault ()
#     yield interface.IERC20(token_address)


@pytest.fixture(scope="session")
def whale(amount, token):
    # Totally in it for the tech
    # Update this with a large holder of your want token (the largest EOA holder of LP)
    whale = accounts.at(
        "0x79eF6103A513951a3b25743DB509E267685726B7", force=True
    )  # 0x79eF6103A513951a3b25743DB509E267685726B7, rETH gauge, fine to use with convex, 40k tokens
    if token.balanceOf(whale) < 2 * amount:
        raise ValueError(
            "Our whale needs more funds. Find another whale or reduce your amount variable."
        )
    yield whale


# this is the amount of funds we have our whale deposit. adjust this as needed based on their wallet balance
@pytest.fixture(scope="session")
def amount(token):
    amount = 10 * 10 ** token.decimals()  # 10 for rETH
    yield amount


@pytest.fixture(scope="session")
def profit_whale(profit_amount, token):
    # ideally not the same whale as the main whale, or else they will lose money
    profit_whale = accounts.at(
        "0xA169c91d692486b8C35E7E17De7D4be743920E37", force=True
    )  # 0xA169c91d692486b8C35E7E17De7D4be743920E37, rETH pool, 10 tokens
    if token.balanceOf(profit_whale) < 5 * profit_amount:
        raise ValueError(
            "Our profit whale needs more funds. Find another whale or reduce your profit_amount variable."
        )
    yield profit_whale


@pytest.fixture(scope="session")
def profit_amount(token):
    profit_amount = 0.1 * 10 ** token.decimals()  # 0.1 for rETH
    yield profit_amount


@pytest.fixture(scope="session")
def to_sweep():
    # token we can sweep out of strategy (use CRV)
    yield interface.IERC20("0xD533a949740bb3306d119CC777fa900bA034cd52")


# set address if already deployed, use ZERO_ADDRESS if not
@pytest.fixture(scope="session")
def vault_address():
    vault_address = ZERO_ADDRESS
    yield vault_address


# if our vault is pre-0.4.3, this will affect a few things
@pytest.fixture(scope="session")
def old_vault():
    old_vault = False
    yield old_vault


# this is the name we want to give our strategy
@pytest.fixture(scope="session")
def strategy_name():
    strategy_name = "StrategyAurarETH"
    yield strategy_name


# this is the name of our strategy in the .sol file
@pytest.fixture(scope="session")
def contract_name(StrategyConvexFactoryClonable):
    contract_name = StrategyConvexFactoryClonable
    yield contract_name


# if our strategy is using ySwaps, then we need to donate profit to it from our profit whale
@pytest.fixture(scope="session")
def use_yswaps():
    use_yswaps = True
    yield use_yswaps


# whether or not a strategy is clonable. if true, don't forget to update what our cloning function is called in test_cloning.py
@pytest.fixture(scope="session")
def is_clonable():
    is_clonable = True
    yield is_clonable


# use this to test our strategy in case there are no profits
@pytest.fixture(scope="session")
def no_profit():
    no_profit = False
    yield no_profit


# use this when we might lose a few wei on conversions between want and another deposit token (like router strategies)
# generally this will always be true if no_profit is true, even for curve/convex since we can lose a wei converting
@pytest.fixture(scope="session")
def is_slippery(no_profit):
    is_slippery = False  # set this to true or false as needed
    if no_profit:
        is_slippery = True
    yield is_slippery


# use this to set the standard amount of time we sleep between harvests.
# generally 1 day, but can be less if dealing with smaller windows (oracles) or longer if we need to trigger weekly earnings.
@pytest.fixture(scope="session")
def sleep_time():
    hour = 3600

    # change this one right here
    hours_to_sleep = 24

    sleep_time = hour * hours_to_sleep
    yield sleep_time


#################### FIXTURES ABOVE NEED TO BE ADJUSTED FOR THIS REPO ####################

#################### FIXTURES BELOW SHOULDN'T NEED TO BE ADJUSTED FOR THIS REPO ####################


@pytest.fixture(scope="session")
def tests_using_tenderly():
    yes_or_no = use_tenderly
    yield yes_or_no


# by default, pytest uses decimals, but in solidity we use uints, so 10 actually equals 10 wei (1e-17 for most assets, or 1e-6 for USDC/USDT)
@pytest.fixture(scope="session")
def RELATIVE_APPROX(token):
    approx = 10
    print("Approx:", approx, "wei")
    yield approx


# use this to set various fixtures that differ by chain
if chain_used == 1:  # mainnet

    @pytest.fixture(scope="session")
    def gov():
        yield accounts.at("0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52", force=True)

    @pytest.fixture(scope="session")
    def health_check():
        yield interface.IHealthCheck("0xddcea799ff1699e98edf118e0629a974df7df012")

    @pytest.fixture(scope="session")
    def base_fee_oracle():
        yield interface.IBaseFeeOracle("0xfeCA6895DcF50d6350ad0b5A8232CF657C316dA7")

    # set all of the following to SMS, just simpler
    @pytest.fixture(scope="session")
    def management():
        yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)

    @pytest.fixture(scope="session")
    def rewards(management):
        yield management

    @pytest.fixture(scope="session")
    def guardian(management):
        yield management

    @pytest.fixture(scope="session")
    def strategist(management):
        yield management

    @pytest.fixture(scope="session")
    def keeper(management):
        yield management

    @pytest.fixture(scope="session")
    def trade_factory():
        yield Contract("0xcADBA199F3AC26F67f660C89d43eB1820b7f7a3b")

    @pytest.fixture(scope="session")
    def keeper_wrapper():
        yield Contract("0x0D26E894C2371AB6D20d99A65E991775e3b5CAd7")


@pytest.fixture(scope="module")
def vault(pm, gov, rewards, guardian, management, token, vault_address):
    if vault_address == ZERO_ADDRESS:
        Vault = pm(config["dependencies"][0]).Vault
        vault = guardian.deploy(Vault)
        vault.initialize(token, gov, rewards, "", "", guardian)
        vault.setDepositLimit(2 ** 256 - 1, {"from": gov})
        vault.setManagement(management, {"from": gov})
    else:
        vault = interface.IVaultFactory045(vault_address)
    yield vault


#################### FIXTURES ABOVE SHOULDN'T NEED TO BE ADJUSTED FOR THIS REPO ####################

#################### FIXTURES BELOW LIKELY NEED TO BE ADJUSTED FOR THIS REPO ####################


# replace the first value with the name of your strategy
@pytest.fixture(scope="module")
def strategy(
    strategist,
    keeper,
    vault,
    gov,
    management,
    health_check,
    contract_name,
    strategy_name,
    base_fee_oracle,
    vault_address,
    trade_factory,
    which_strategy,
    pid,
    gauge,
    new_proxy,
    voter,
    convex_token,
    booster,
    has_rewards,
    rewards_token,
):

    if which_strategy == 0:  # convex
        strategy = gov.deploy(
            contract_name,
            vault,
            trade_factory,
            pid,
            10_000 * 1e6,
            25_000 * 1e6,
            booster,
            convex_token,
        )
    elif which_strategy == 1:  # curve
        strategy = gov.deploy(
            contract_name,
            vault,
            trade_factory,
            new_proxy,
            gauge,
        )
        voter.setStrategy(new_proxy.address, {"from": gov})
        print("New Strategy Proxy setup")

    strategy.setKeeper(keeper, {"from": gov})

    # set our management fee to zero so it doesn't mess with our profit checking
    vault.setManagementFee(0, {"from": gov})
    vault.setPerformanceFee(0, {"from": gov})

    # we will be migrating on our live vault instead of adding it directly
    if which_strategy == 0:  # convex
        # earmark rewards if we are using a convex strategy
        booster.earmarkRewards(pid, {"from": gov})
        chain.sleep(1)
        chain.mine(1)

        vault.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, 0, {"from": gov})
        print("New Vault, Convex Strategy")
        chain.sleep(1)
        chain.mine(1)

        # this is the same for new or existing vaults
        strategy.setHarvestTriggerParams(
            90000e6, 150000e6, strategy.checkEarmark(), {"from": gov}
        )
    elif which_strategy == 1:  # Curve
        vault.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, 0, {"from": gov})
        print("New Vault, Curve Strategy")
        chain.sleep(1)
        chain.mine(1)

        # approve reward token on our strategy proxy if needed
        if has_rewards:
            # first, add our rewards token to our strategy, then use that for our strategy proxy
            strategy.updateRewards([rewards_token], {"from": gov})
            new_proxy.approveRewardToken(strategy.rewardsTokens(0), {"from": gov})

        # approve our new strategy on the proxy
        new_proxy.approveStrategy(strategy.gauge(), strategy, {"from": gov})
        assert new_proxy.strategies(gauge.address) == strategy.address
        assert voter.strategy() == new_proxy.address

    # turn our oracle into testing mode by setting the provider to 0x00, then forcing true
    strategy.setBaseFeeOracle(base_fee_oracle, {"from": management})
    base_fee_oracle.setBaseFeeProvider(ZERO_ADDRESS, {"from": management})
    base_fee_oracle.setManualBaseFeeBool(True, {"from": management})
    assert strategy.isBaseFeeAcceptable() == True

    yield strategy


#################### FIXTURES ABOVE LIKELY NEED TO BE ADJUSTED FOR THIS REPO ####################

####################         PUT UNIQUE FIXTURES FOR THIS REPO BELOW         ####################

# put our test pool's convex pid here
# if you change this, make sure to update addresses/values below too
@pytest.fixture(scope="session")
def pid():
    pid = 15  # 15 rETH-WETH
    yield pid


# put our test pool's convex pid here
@pytest.fixture(scope="session")
def test_pid():
    test_pid = 2  # 2 bbUSD
    yield test_pid


# must be 0, 1, or 2 for convex, curve, and frax. Only test 2 (Frax) for pools that actually have frax (not balancer).
@pytest.fixture(scope="session")
def which_strategy():
    which_strategy = 0
    yield which_strategy


# this is the address of our rewards token
@pytest.fixture(scope="session")
def rewards_token():  # OGN 0x8207c1FfC5B6804F6024322CcF34F29c3541Ae26, SPELL 0x090185f2135308BaD17527004364eBcC2D37e5F6
    # SNX 0xC011a73ee8576Fb46F5E1c5751cA3B9Fe0af2a6F, ANGLE 0x31429d1856aD1377A8A0079410B297e1a9e214c2, LDO 0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32
    yield Contract("0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32")


# sUSD gauge uses blocks instead of seconds to determine rewards, so this needs to be true for that to test if we're earning
@pytest.fixture(scope="session")
def try_blocks():
    try_blocks = False  # True for sUSD
    yield try_blocks


# whether or not we should try a test donation of our rewards token to make sure the strategy handles them correctly
# if you want to bother with whale and amount below, this needs to be true
@pytest.fixture(scope="session")
def test_donation():
    test_donation = False
    yield test_donation


@pytest.fixture(scope="session")
def rewards_whale(accounts):
    # SNX whale: 0x8D6F396D210d385033b348bCae9e4f9Ea4e045bD, >600k SNX
    # SPELL whale: 0x46f80018211D5cBBc988e853A8683501FCA4ee9b, >10b SPELL
    # ANGLE whale: 0x2Fc443960971e53FD6223806F0114D5fAa8C7C4e, 11.6m ANGLE
    yield accounts.at("0x2Fc443960971e53FD6223806F0114D5fAa8C7C4e", force=True)


@pytest.fixture(scope="session")
def rewards_amount():
    rewards_amount = 10_000_000e18
    # SNX 50_000e18
    # SPELL 1_000_000e18
    # ANGLE 10_000_000e18
    yield rewards_amount


# whether or not a strategy has ever had rewards, even if they are zero currently. essentially checking if the infra is there for rewards.
@pytest.fixture(scope="session")
def rewards_template():
    rewards_template = False
    yield rewards_template


# this is whether our pool currently has extra reward emissions (SNX, SPELL, etc)
@pytest.fixture(scope="session")
def has_rewards():
    has_rewards = False
    yield has_rewards


# if our curve gauge deposits aren't tokenized (older pools), we can't as easily do some tests and we skip them
@pytest.fixture(scope="session")
def gauge_is_not_tokenized():
    gauge_is_not_tokenized = False
    yield gauge_is_not_tokenized


########## ADDRESSES TO UPDATE FOR BALANCER VS CURVE ##########

# all contracts below should be able to stay static based on the pid
@pytest.fixture(scope="session")
def booster():  # this is the deposit contract
    yield Contract("0xA57b8d98dAE62B26Ec3bcC4a365338157060B234")


# balancer voter!
@pytest.fixture(scope="session")
def voter():
    yield Contract("0xBA11E7024cbEB1dd2B401C70A83E0d964144686C")


@pytest.fixture(scope="session")
def convex_token():
    yield Contract("0xC0c293ce456fF0ED870ADd98a0828Dd4d2903DBF")


@pytest.fixture(scope="session")
def crv():
    yield Contract("0xba100000625a3754423978a60c9317c58a424e3D")


@pytest.fixture(scope="session")
def fxs():
    yield Contract("0x3432B6A60D23Ca0dFCa7761B7ab56459D9C964D0")


@pytest.fixture(scope="session")
def crv_whale():
    yield accounts.at("0x740a4AEEfb44484853AA96aB12545FC0290805F3", force=True)


@pytest.fixture(scope="session")
def test_vault():  # bb-USD
    yield Contract("0xc5F3D11580c41cD07104e9AF154Fc6428bb93c73")


@pytest.fixture(scope="session")
def test_gauge():  # bb-USD
    yield Contract("0xa6325e799d266632D347e41265a69aF111b05403")


@pytest.fixture(scope="session")
def fud_gauge():  # FIAT-USD
    yield Contract("0xDD4Db3ff8A37FE418dB6FF34fC316655528B6bbC")


@pytest.fixture(scope="session")
def fud_lp():  # FIAT-USD
    yield Contract("0x178E029173417b1F9C8bC16DCeC6f697bC323746")


@pytest.fixture(scope="session")
def token(pid, booster):
    # this should be the address of the ERC-20 used by the strategy/vault
    token_address = booster.poolInfo(pid)[0]
    yield Contract(token_address)


@pytest.fixture(scope="session")
def cvx_deposit(booster, pid):
    # this should be the address of the convex deposit token
    cvx_address = booster.poolInfo(pid)[1]
    yield Contract(cvx_address)


@pytest.fixture(scope="session")
def rewards_contract(pid, booster):
    rewards_contract = booster.poolInfo(pid)[3]
    yield Contract(rewards_contract)


# gauge for the curve pool
@pytest.fixture(scope="session")
def gauge(pid, booster):
    gauge = booster.poolInfo(pid)[2]
    yield Contract(gauge)


@pytest.fixture(scope="module")
def convex_template(
    StrategyConvexFactoryClonable,
    trade_factory,
    test_vault,
    gov,
    booster,
    convex_token,
    test_pid,
):
    # deploy our convex template
    convex_template = gov.deploy(
        StrategyConvexFactoryClonable,
        test_vault,
        trade_factory,
        test_pid,
        10_000 * 1e6,
        25_000 * 1e6,
        booster,
        convex_token,
    )
    print("\nConvex Template deployed:", convex_template)

    yield convex_template


@pytest.fixture(scope="module")
def curve_template(
    StrategyCurveBoostedFactoryClonable,
    trade_factory,
    test_vault,
    strategist,
    test_gauge,
    new_proxy,
    gov,
):
    # deploy our curve template
    curve_template = gov.deploy(
        StrategyCurveBoostedFactoryClonable,
        test_vault,
        trade_factory,
        new_proxy,
        test_gauge,
    )
    print("Curve Template deployed:", curve_template)

    yield curve_template


@pytest.fixture(scope="module")
def curve_global(
    BalancerGlobal,
    new_registry,
    gov,
    convex_template,
    curve_template,
):
    # deploy our factory
    curve_global = gov.deploy(
        BalancerGlobal,
        new_registry,
        convex_template,
        curve_template,
        gov,
    )

    print("Balancer factory deployed:", curve_global)
    yield curve_global


@pytest.fixture(scope="module")
def new_proxy(StrategyProxy, gov):
    # deploy our new strategy proxy for our balancer voter
    strategy_proxy = gov.deploy(StrategyProxy)

    print("New Strategy Proxy deployed:", strategy_proxy)
    yield strategy_proxy


@pytest.fixture(scope="session")
def new_registry(VaultRegistry):
    yield VaultRegistry.at("0xaF1f5e1c19cB68B30aAD73846eFfDf78a5863319")


@pytest.fixture(scope="session")
def destination_strategy():
    # destination strategy of the route
    yield interface.ICurveStrategy045("0x83D0458e627cFD7C6d0da12a1223bd168e1c8B64")
