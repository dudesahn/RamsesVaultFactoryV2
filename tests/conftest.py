import pytest
from brownie import config, Contract, ZERO_ADDRESS, chain, interface, accounts
from eth_abi import encode_single
import requests
from utils import create_whale, create_stable_lp_whale, create_velo_lp_whale

# Snapshots the chain before each test and reverts after test completion.
@pytest.fixture(scope="function", autouse=True)
def isolate(fn_isolation):
    pass


# set this for if we want to use tenderly or not; mostly helpful because with brownie.reverts fails in tenderly forks.
use_tenderly = False

# use this to set what chain we use. 1 for ETH, 250 for fantom, 10 optimism, 42161 arbitrum
chain_used = 10


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


@pytest.fixture(scope="session")
def token():
    token_address = "0x615B9dd61f1F9a80f5bcD33A53Eb79c37b20adDC"  # this should be the address of the ERC-20 used by the strategy/vault (BLU/USDC LP)
    yield interface.IVeloPoolV2(token_address)


# v2 velo/usdc pool: 0x8134A2fDC127549480865fB8E5A9E8A8a95a54c5 (liq here to swap fine)
# will need to add liq to v2 BLU/USDC
# v1 pool factory: 0x25CbdDb98b35ab1FF77413456B31EC81A6B6B746
# v2 pool factory: 0xF1046053aa5682b4F9a81b5481394DA16BE5FF5a
# v2 BLUE/USDC pool: 0x615B9dd61f1F9a80f5bcD33A53Eb79c37b20adDC
# v1 BLUE/USDC pool: 0x662f16652A242aaD3C938c80864688e4d9B26A5e


@pytest.fixture(scope="function")
def whale(amount, token, gauge):
    # Totally in it for the tech
    # Update this with a large holder of your want token (the largest EOA holder of LP)
    whale = accounts.at(
        "0x662f16652A242aaD3C938c80864688e4d9B26A5e", force=True
    )  # 0x662f16652A242aaD3C938c80864688e4d9B26A5e, blu/USDC v1 pool

    # make sure we'll have enough tokens
    create_whale(token, whale, gauge)

    if token.balanceOf(whale) < 2 * amount:
        raise ValueError(
            "Our whale needs more funds. Find another whale or reduce your amount variable."
        )
    yield whale


# this is the amount of funds we have our whale deposit. adjust this as needed based on their wallet balance
@pytest.fixture(scope="function")
def amount(token):
    amount = 0.3 * 10 ** token.decimals()  # 0.3 for blu/usdc!
    yield amount


@pytest.fixture(scope="function")
def profit_whale(profit_amount, token, whale):
    # ideally not the same whale as the main whale, or else they will lose money
    profit_whale = accounts.at(
        "0x662f16652A242aaD3C938c80864688e4d9B26A5e", force=True
    )  # 0x662f16652A242aaD3C938c80864688e4d9B26A5e, rETH pool, 7.7 tokens
    if token.balanceOf(profit_whale) < 5 * profit_amount:
        raise ValueError(
            "Our profit whale needs more funds. Find another whale or reduce your profit_amount variable."
        )
    yield profit_whale


@pytest.fixture(scope="function")
def profit_amount(token):
    profit_amount = 0.000001 * 10 ** token.decimals()
    yield profit_amount


@pytest.fixture(scope="session")
def to_sweep(crv):
    # token we can sweep out of strategy (use CRV)
    yield crv


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
    strategy_name = "StrategyVelodromeClonable"
    yield strategy_name


# this is the name of our strategy in the .sol file
@pytest.fixture(scope="session")
def contract_name(
    StrategyVelodromeFactoryClonable,
    which_strategy,
):
    contract_name = StrategyVelodromeFactoryClonable
    yield contract_name


# if our strategy is using ySwaps, then we need to donate profit to it from our profit whale
@pytest.fixture(scope="session")
def use_yswaps():
    use_yswaps = False
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
    hours_to_sleep = 12

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

elif chain_used == 10:  # optimism

    @pytest.fixture(scope="session")
    def gov():
        yield accounts.at("0xF5d9D6133b698cE29567a90Ab35CfB874204B3A7", force=True)

    @pytest.fixture(scope="session")
    def health_check():
        yield interface.IHealthCheck("0x3d8F58774611676fd196D26149C71a9142C45296")

    @pytest.fixture(scope="session")
    def base_fee_oracle():
        yield interface.IBaseFeeOracle("0xbf4A735F123A9666574Ff32158ce2F7b7027De9A")

    # set all of the following to Scream Guardian MS
    @pytest.fixture(scope="session")
    def management():
        yield accounts.at("0xea3a15df68fCdBE44Fdb0DB675B2b3A14a148b26", force=True)

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
    def to_sweep():
        # token we can sweep out of strategy (use VELO v2)
        yield interface.IERC20("0x9560e827aF36c94D2Ac33a39bCE1Fe78631088Db")

    @pytest.fixture(scope="session")
    def keeper_wrapper(KeeperWrapper):
        yield KeeperWrapper.at("0x9Ce0115381f009E382acd52761127eFF61061482")


@pytest.fixture(scope="function")
def vault(pm, gov, rewards, guardian, management, token, vault_address):
    if vault_address == ZERO_ADDRESS:
        Vault = pm(config["dependencies"][0]).Vault
        vault = guardian.deploy(Vault)
        vault.initialize(token, gov, rewards, "", "", guardian)
        vault.setDepositLimit(2**256 - 1, {"from": gov})
        vault.setManagement(management, {"from": gov})
    else:
        vault = interface.IVaultFactory045(vault_address)
    yield vault


#################### FIXTURES ABOVE SHOULDN'T NEED TO BE ADJUSTED FOR THIS REPO ####################

#################### FIXTURES BELOW LIKELY NEED TO BE ADJUSTED FOR THIS REPO ####################

# use this similarly to how we use use_yswaps
@pytest.fixture(scope="session")
def is_gmx():
    yield False


@pytest.fixture(scope="session")
def target():
    # whatever we want it to be—this is passed into our harvest function as a target
    yield 9


# this should be a strategy from a different vault to check during migration
@pytest.fixture(scope="session")
def other_strategy():
    yield Contract("0x4809143428Ed49D08978aDF209A4179d52ce5371")


# replace the first value with the name of your strategy
@pytest.fixture(scope="function")
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
    which_strategy,
    gauge,
    route0,
    route1,
):
    strategy = gov.deploy(
        contract_name,
        vault,
        gauge,
        route0,
        route1,
    )
    strategy.setKeeper(keeper, {"from": gov})

    # set our management fee to zero so it doesn't mess with our profit checking
    vault.setManagementFee(0, {"from": gov})
    vault.setPerformanceFee(0, {"from": gov})

    vault.addStrategy(strategy, 10_000, 0, 2**256 - 1, 0, {"from": gov})
    print("New Vault, Velo Strategy")
    chain.sleep(1)
    chain.mine(1)

    # turn our oracle into testing mode by setting the provider to 0x00, then forcing true
    strategy.setBaseFeeOracle(base_fee_oracle, {"from": management})
    base_fee_oracle.setBaseFeeProvider(
        ZERO_ADDRESS, {"from": base_fee_oracle.governance()}
    )
    base_fee_oracle.setManualBaseFeeBool(True, {"from": base_fee_oracle.governance()})
    assert strategy.isBaseFeeAcceptable() == True

    yield strategy


#################### FIXTURES ABOVE LIKELY NEED TO BE ADJUSTED FOR THIS REPO ####################

####################         PUT UNIQUE FIXTURES FOR THIS REPO BELOW         ####################


@pytest.fixture(scope="session")
def v1_pool_factory():
    yield "0x25CbdDb98b35ab1FF77413456B31EC81A6B6B746"


@pytest.fixture(scope="session")
def v2_pool_factory():
    yield "0xF1046053aa5682b4F9a81b5481394DA16BE5FF5a"


# route to swap from VELO v2 to USDC
@pytest.fixture(scope="session")
def route0(dola, usdc, blue, to_sweep, v2_pool_factory, v1_pool_factory):
    route0 = [(to_sweep.address, usdc, False, v2_pool_factory)]
    yield route0


# route to swap from VELO v2 to BLU (on v2)
@pytest.fixture(scope="session")
def route1(dola, usdc, blue, to_sweep, v2_pool_factory, v1_pool_factory):
    route1 = [
        (to_sweep.address, usdc, False, v2_pool_factory),
        (usdc, blue, False, v2_pool_factory),
    ]
    yield route1


@pytest.fixture(scope="session")
def usdc():
    yield "0x7F5c764cBc14f9669B88837ca1490cCa17c31607"


@pytest.fixture(scope="session")
def dola():
    yield "0x8aE125E8653821E851F12A49F7765db9a9ce7384"


@pytest.fixture(scope="session")
def blue():
    yield "0xa50B23cDfB2eC7c590e84f403256f67cE6dffB84"


# we don't use this, set it to 0 though since that's the index of our strategy
@pytest.fixture(scope="session")
def which_strategy():
    which_strategy = 1
    yield which_strategy


# gauge for the curve pool
@pytest.fixture(scope="session")
def gauge():
    gauge = "0x8166f06D50a65F82850878c951fcA29Af5Ea7Db2"  # v2 BLU/USDC
    yield Contract(gauge)


# template vault just so we can create a template strategy for cloning
@pytest.fixture(scope="session")
def template_vault():
    template_vault = "0xde8747070f81a5217bd812d3833F725f588E3dec"
    yield template_vault


# gauge for our template vault pool
@pytest.fixture(scope="session")
def template_gauge():
    template_gauge = "0x84195De69B8B131ddAa4Be4F75633fCD7F430b7c"  # VELO-USDC v2
    yield template_gauge


# route to swap from VELO v2 to USDC
@pytest.fixture(scope="session")
def template_route0(dola, usdc, blue, to_sweep, v2_pool_factory, v1_pool_factory):
    template_route0 = [
        (to_sweep.address, usdc, False, v2_pool_factory),
    ]
    yield template_route0


# route to swap from VELO v2 to...itself
@pytest.fixture(scope="session")
def template_route1(dola, usdc, blue, to_sweep, v2_pool_factory, v1_pool_factory):
    template_route1 = []
    yield template_route1


# route to swap from VELO v2 to DOLA
@pytest.fixture(scope="session")
def random_route_1(dola, usdc, blue, to_sweep, v2_pool_factory, v1_pool_factory):
    random_route_1 = [
        (to_sweep.address, usdc, False, v2_pool_factory),
        (usdc, dola, False, v1_pool_factory),
    ]
    yield random_route_1


# route to swap from DOLA to VELO
@pytest.fixture(scope="session")
def random_route_2(dola, usdc, blue, to_sweep, v2_pool_factory, v1_pool_factory):
    random_route_2 = [
        (dola, usdc, True, v1_pool_factory),
        (usdc, to_sweep.address, False, v2_pool_factory),
    ]
    yield random_route_2


@pytest.fixture(scope="function")
def velo_template(
    StrategyVelodromeFactoryClonable,
    template_vault,
    strategist,
    template_gauge,
    gov,
    template_route0,
    template_route1,
):
    # deploy our curve template
    velo_template = gov.deploy(
        StrategyVelodromeFactoryClonable,
        template_vault,
        template_gauge,
        template_route0,
        template_route1,
    )
    print("Velo Template deployed:", velo_template)

    yield velo_template


@pytest.fixture(scope="function")
def velo_global(
    VelodromeGlobal,
    new_registry,
    gov,
    velo_template,
):
    # deploy our factory
    velo_global = gov.deploy(
        VelodromeGlobal,
        new_registry,
        velo_template,
        gov,
    )

    print("Velodrome factory deployed:", velo_global)
    yield velo_global


@pytest.fixture(scope="session")
def new_registry():
    yield Contract("0x79286Dd38C9017E5423073bAc11F53357Fc5C128")


################# USE THESE VARS FOR TESTING HOW OTHER LP TOKENS WOULD FUNCTION #################

################# STABLE POOL #################

# gauge for the curve pool
@pytest.fixture(scope="session")
def stable_gauge():
    stable_gauge = "0xa1034Ed2C9eb616d6F7f318614316e64682e7923"  # v2 USDC/DOLA
    yield interface.IVeloV2Gauge(stable_gauge)


@pytest.fixture(scope="session")
def stable_token():
    stable_token = "0xB720FBC32d60BB6dcc955Be86b98D8fD3c4bA645"  # this should be the address of the ERC-20 used by the strategy/vault (USDC/DOLA LP)
    yield interface.IVeloPoolV2(stable_token)


# route to swap from VELO v2 to USDC
@pytest.fixture(scope="session")
def stable_route0(dola, usdc, blue, to_sweep, v2_pool_factory, v1_pool_factory):
    stable_route0 = [
        (to_sweep.address, usdc, False, v2_pool_factory),
    ]
    yield stable_route0


# route to swap from VELO v2 to DOLA
@pytest.fixture(scope="session")
def stable_route1(dola, usdc, blue, to_sweep, v2_pool_factory, v1_pool_factory):
    # need to use v2 for USDC -> DOLA since we use v1 as our whale
    stable_route1 = [
        (to_sweep.address, usdc, False, v2_pool_factory),
        (usdc, dola, True, v2_pool_factory),
    ]
    yield stable_route1


@pytest.fixture(scope="function")
def stable_whale(stable_amount, stable_token, stable_gauge):
    # Totally in it for the tech
    # Update this with a large holder of your want token (the largest EOA holder of LP)
    stable_whale = accounts.at(
        "0x6C5019D345Ec05004A7E7B0623A91a0D9B8D590d", force=True
    )  # 0x6C5019D345Ec05004A7E7B0623A91a0D9B8D590d, USDC/DOLA v1 pool

    # make sure we'll have enough tokens
    create_stable_lp_whale(stable_token, stable_whale, stable_gauge)

    if stable_token.balanceOf(stable_whale) < 2 * stable_amount:
        raise ValueError(
            "Our whale needs more funds. Find another whale or reduce your amount variable."
        )
    yield stable_whale


# this is the amount of funds we have our whale deposit. adjust this as needed based on their wallet balance
@pytest.fixture(scope="function")
def stable_amount(stable_token):
    stable_amount = 1 * 10 ** stable_token.decimals()  # 1 for DOLA/USDC
    yield stable_amount


@pytest.fixture(scope="function")
def stable_profit_whale(stable_profit_amount, stable_token):
    # ideally not the same whale as the main whale, or else they will lose money
    profit_whale = accounts.at(
        "0x6C5019D345Ec05004A7E7B0623A91a0D9B8D590d", force=True
    )  # 0x6C5019D345Ec05004A7E7B0623A91a0D9B8D590d,
    if stable_token.balanceOf(profit_whale) < 5 * stable_profit_amount:
        raise ValueError(
            "Our profit whale needs more funds. Find another whale or reduce your profit_amount variable."
        )
    yield profit_whale


# this is the amount of funds we have our whale deposit. adjust this as needed based on their wallet balance
@pytest.fixture(scope="function")
def stable_profit_amount(stable_token):
    stable_profit_amount = (
        0.0000003 * 10 ** stable_token.decimals()
    )  # 0.003 for DOLA/MAI
    yield stable_profit_amount


@pytest.fixture(scope="function")
def stable_vault(pm, gov, rewards, guardian, management, stable_token, vault_address):
    token = stable_token
    if vault_address == ZERO_ADDRESS:
        Vault = pm(config["dependencies"][0]).Vault
        stable_vault = guardian.deploy(Vault)
        stable_vault.initialize(token, gov, rewards, "", "", guardian)
        stable_vault.setDepositLimit(2**256 - 1, {"from": gov})
        stable_vault.setManagement(management, {"from": gov})
    else:
        stable_vault = interface.IVaultFactory045(vault_address)
    yield stable_vault


# replace the first value with the name of your strategy
@pytest.fixture(scope="function")
def stable_strategy(
    strategist,
    keeper,
    stable_vault,
    gov,
    management,
    health_check,
    contract_name,
    strategy_name,
    base_fee_oracle,
    vault_address,
    which_strategy,
    stable_gauge,
    stable_route0,
    stable_route1,
):
    vault = stable_vault
    strategy = gov.deploy(
        contract_name,
        vault,
        stable_gauge,
        stable_route0,
        stable_route1,
    )
    strategy.setKeeper(keeper, {"from": gov})

    # set our management fee to zero so it doesn't mess with our profit checking
    vault.setManagementFee(0, {"from": gov})
    vault.setPerformanceFee(0, {"from": gov})

    vault.addStrategy(strategy, 10_000, 0, 2**256 - 1, 0, {"from": gov})

    print("New Vault, Velo Strategy")
    chain.sleep(1)
    chain.mine(1)

    # turn our oracle into testing mode by setting the provider to 0x00, then forcing true
    strategy.setBaseFeeOracle(base_fee_oracle, {"from": management})
    base_fee_oracle.setBaseFeeProvider(
        ZERO_ADDRESS, {"from": base_fee_oracle.governance()}
    )
    base_fee_oracle.setManualBaseFeeBool(True, {"from": base_fee_oracle.governance()})
    assert strategy.isBaseFeeAcceptable() == True

    yield strategy


################# VELO POOL #################

# gauge for the curve pool
@pytest.fixture(scope="session")
def velo_gauge():
    velo_gauge = "0x84195De69B8B131ddAa4Be4F75633fCD7F430b7c"  # v2 USDC/VELO
    yield interface.IVeloV2Gauge(velo_gauge)


@pytest.fixture(scope="session")
def velo_token():
    velo_token = "0x8134A2fDC127549480865fB8E5A9E8A8a95a54c5"  # this should be the address of the ERC-20 used by the strategy/vault (USDC/VELOv2 LP)
    yield interface.IVeloPoolV2(velo_token)


# route to swap from VELO v2 to USDC
@pytest.fixture(scope="session")
def velo_route0(dola, usdc, blue, to_sweep, v2_pool_factory, v1_pool_factory):
    velo_route0 = [
        (to_sweep.address, usdc, False, v2_pool_factory),
    ]
    yield velo_route0


# route to swap from VELO v2 to DOLA
@pytest.fixture(scope="session")
def velo_route1(dola, usdc, blue, to_sweep, v2_pool_factory, v1_pool_factory):
    # need to use v2 for USDC -> DOLA since we use v1 as our whale
    velo_route1 = []
    yield velo_route1


@pytest.fixture(scope="function")
def velo_whale(velo_amount, velo_token, velo_gauge):
    # Totally in it for the tech
    # Update this with a large holder of your want token (the largest EOA holder of LP)
    velo_whale = accounts.at(
        "0xEdDc3369E15E9EfFa6e1eC2eE1ddc3CDf501E852", force=True
    )  # 0xEdDc3369E15E9EfFa6e1eC2eE1ddc3CDf501E852, USDC/DOLA v1 pool

    # make sure we'll have enough tokens
    create_velo_lp_whale(velo_token, velo_whale, velo_gauge)

    if velo_token.balanceOf(velo_whale) < 2 * velo_amount:
        raise ValueError(
            "Our whale needs more funds. Find another whale or reduce your amount variable."
        )
    yield velo_whale


# this is the amount of funds we have our whale deposit. adjust this as needed based on their wallet balance
@pytest.fixture(scope="function")
def velo_amount(velo_token):
    velo_amount = 0.05 * 10 ** velo_token.decimals()  # 0.05 for VELO/USDC
    yield velo_amount


@pytest.fixture(scope="function")
def velo_profit_whale(velo_profit_amount, velo_token):
    # ideally not the same whale as the main whale, or else they will lose money
    profit_whale = accounts.at(
        "0xEdDc3369E15E9EfFa6e1eC2eE1ddc3CDf501E852", force=True
    )  # 0xEdDc3369E15E9EfFa6e1eC2eE1ddc3CDf501E852,
    if velo_token.balanceOf(profit_whale) < 5 * velo_profit_amount:
        raise ValueError(
            "Our profit whale needs more funds. Find another whale or reduce your profit_amount variable."
        )
    yield profit_whale


# this is the amount of funds we have our whale deposit. adjust this as needed based on their wallet balance
@pytest.fixture(scope="function")
def velo_profit_amount(velo_token):
    velo_profit_amount = 0.0000003 * 10 ** velo_token.decimals()  # 0.003 for DOLA/MAI
    yield velo_profit_amount


@pytest.fixture(scope="function")
def velo_vault(pm, gov, rewards, guardian, management, velo_token, vault_address):
    token = velo_token
    if vault_address == ZERO_ADDRESS:
        Vault = pm(config["dependencies"][0]).Vault
        velo_vault = guardian.deploy(Vault)
        velo_vault.initialize(token, gov, rewards, "", "", guardian)
        velo_vault.setDepositLimit(2**256 - 1, {"from": gov})
        velo_vault.setManagement(management, {"from": gov})
    else:
        velo_vault = interface.IVaultFactory045(vault_address)
    yield velo_vault


# replace the first value with the name of your strategy
@pytest.fixture(scope="function")
def velo_strategy(
    strategist,
    keeper,
    velo_vault,
    gov,
    management,
    health_check,
    contract_name,
    strategy_name,
    base_fee_oracle,
    vault_address,
    which_strategy,
    velo_gauge,
    velo_route0,
    velo_route1,
):
    vault = velo_vault
    strategy = gov.deploy(
        contract_name,
        vault,
        velo_gauge,
        velo_route0,
        velo_route1,
    )
    strategy.setKeeper(keeper, {"from": gov})

    # set our management fee to zero so it doesn't mess with our profit checking
    vault.setManagementFee(0, {"from": gov})
    vault.setPerformanceFee(0, {"from": gov})

    vault.addStrategy(strategy, 10_000, 0, 2**256 - 1, 0, {"from": gov})

    print("New Vault, Velo Strategy")
    chain.sleep(1)
    chain.mine(1)

    # turn our oracle into testing mode by setting the provider to 0x00, then forcing true
    strategy.setBaseFeeOracle(base_fee_oracle, {"from": management})
    base_fee_oracle.setBaseFeeProvider(
        ZERO_ADDRESS, {"from": base_fee_oracle.governance()}
    )
    base_fee_oracle.setManualBaseFeeBool(True, {"from": base_fee_oracle.governance()})
    assert strategy.isBaseFeeAcceptable() == True

    yield strategy
