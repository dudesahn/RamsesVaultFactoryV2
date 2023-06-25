import brownie
from brownie import Contract, ZERO_ADDRESS, interface, chain, accounts
import math
import pytest


def test_vault_deployment(
    StrategyVelodromeFactoryClonable,
    strategist,
    velo_global,
    gov,
    guardian,
    token,
    health_check,
    base_fee_oracle,
    new_registry,
    gauge,
    whale,
    tests_using_tenderly,
    keeper_wrapper,
    amount,
    route0,
    route1,
):
    # once our factory is deployed, setup the factory from gov
    registry_owner = accounts.at(new_registry.owner(), force=True)
    new_registry.setApprovedVaultsOwner(velo_global, True, {"from": registry_owner})
    new_registry.setVaultEndorsers(velo_global, True, {"from": registry_owner})

    # make sure our curve global can own vaults and endorse them
    assert new_registry.approvedVaultsOwner(velo_global)
    assert new_registry.vaultEndorsers(velo_global)
    assert velo_global.registry() == new_registry.address
    print("Our factory can endorse vaults")

    print("Let's deploy this vault")
    print("Factory address: ", velo_global)
    print("Gauge: ", gauge)

    # make sure we can create this vault permissionlessly
    assert velo_global.canCreateVaultPermissionlessly(gauge)

    # turn on keeps
    velo_global.setKeepVELO(69, velo_global.veloVoter(), {"from": gov})
    print(
        "Set our global keeps, don't mess with curve voter or we will revert on deploy"
    )

    tx = velo_global.createNewVaultsAndStrategies(
        gauge, route0, route1, {"from": whale}
    )
    assert velo_global.latestStandardVaultFromGauge(gauge) != ZERO_ADDRESS

    vault_address = tx.events["NewAutomatedVault"]["vault"]
    vault = Contract(vault_address)
    print("Vault name:", vault.name())

    print("Vault endorsed:", vault_address)
    info = tx.events["NewAutomatedVault"]

    print("Here's our new vault created event:", info, "\n")

    # check that everything is setup properly for our vault
    assert vault.governance() == velo_global.address
    assert vault.management() == velo_global.management()
    assert vault.guardian() == velo_global.guardian()
    assert vault.guardian() == velo_global.guardian()
    assert vault.depositLimit() == velo_global.depositLimit()
    assert vault.rewards() == velo_global.treasury()
    assert vault.managementFee() == velo_global.managementFee()
    assert vault.performanceFee() == velo_global.performanceFee()

    # check that things are good on our strategies
    curve_strat = tx.events["NewAutomatedVault"]["veloStrategy"]
    if curve_strat != ZERO_ADDRESS:
        curve_strategy = StrategyVelodromeClonable.at(curve_strat)
        # curve
        assert vault.withdrawalQueue(0) == curve_strat
        assert vault.strategies(curve_strat)["performanceFee"] == 0
        assert curve_strategy.creditThreshold() == 5e22
        assert curve_strategy.healthCheck() == velo_global.healthCheck()
        assert curve_strategy.localkeepVELO() == velo_global.keepVELO()
        assert curve_strategy.veloVoter() == velo_global.veloVoter()
        assert curve_strategy.rewards() == velo_global.treasury()
        assert curve_strategy.strategist() == velo_global.management()
        assert curve_strategy.keeper() == velo_global.keeper()

    # daddy needs to accept gov on all new vaults
    vault.acceptGovernance({"from": gov})
    assert vault.governance() == gov.address

    # check that anyone can harvest a strategy thanks to our keeper wrapper
    print(
        "Check out our keeper wrapper, make sure it works as intended for all strategies"
    )
    rando = accounts[5]
    assert curve_strategy.keeper() == keeper_wrapper
    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})

    keeper_wrapper.harvest(convex_strategy, {"from": rando})
    if curve_strat != ZERO_ADDRESS:
        keeper_wrapper.harvest(curve_strategy, {"from": rando})

    # assert that money deposited to convex
    assert convex_strategy.stakedBalance() > 0

    # wait a week for our funds to unlock
    chain.sleep(86400 * 7)
    chain.mine(1)

    assert not velo_global.canCreateVaultPermissionlessly(gauge)
    assert velo_global.latestStandardVaultFromGauge(gauge) != ZERO_ADDRESS
    print("Can't create another of the same vault permissionlessly")

    if not tests_using_tenderly:
        # can't deploy another of the same vault permissionlessly
        with brownie.reverts("Vault already exists"):
            tx = velo_global.createNewVaultsAndStrategies(gauge, {"from": whale})

        # we can't do our previously existing vault either
        with brownie.reverts("Vault already exists"):
            tx = velo_global.createNewVaultsAndStrategies(fud_gauge, {"from": whale})


def test_permissioned_vault(
    StrategyVelodromeClonable,
    strategist,
    velo_global,
    gov,
    guardian,
    token,
    health_check,
    base_fee_oracle,
    new_registry,
    gauge,
    voter,
    whale,
    tests_using_tenderly,
):
    # deploying curve global with frax strategies doesn't work unless with tenderly;
    # ganache crashes because of the try-catch in the fraxPid function
    # however, I usually do hacky coverage testing (commenting out section in curveGlobal)

    # once our factory is deployed, setup the factory from gov
    registry_owner = accounts.at(new_registry.owner(), force=True)
    new_registry.setApprovedVaultsOwner(velo_global, True, {"from": registry_owner})
    new_registry.setVaultEndorsers(velo_global, True, {"from": registry_owner})

    # make sure our curve global can own vaults and endorse them
    assert new_registry.approvedVaultsOwner(velo_global)
    assert new_registry.vaultEndorsers(velo_global)
    assert velo_global.registry() == new_registry.address
    print("Our factory can endorse vaults")

    print("Let's deploy this vault")
    print("Factory address: ", velo_global)
    print("Gauge: ", gauge)

    # check if we can create this vault permissionlessly
    print(
        "Can we create this vault permissionlessly?",
        velo_global.canCreateVaultPermissionlessly(gauge),
    )

    # turn on keeps
    velo_global.setkeepVELO(69, velo_global.veloVoter(), {"from": gov})
    velo_global.setKeepCVX(69, gov, {"from": gov})
    print(
        "Set our global keeps, don't mess with curve voter or we will revert on deploy"
    )

    # make sure not just anyone can create a permissioned vault
    if not tests_using_tenderly:
        with brownie.reverts():
            velo_global.createNewVaultsAndStrategiesPermissioned(
                gauge, "poop", "poop", {"from": whale}
            )

    if not tests_using_tenderly:
        with brownie.reverts():
            velo_global.createNewVaultsAndStrategiesPermissioned(
                health_check, "poop", "poop", {"from": velo_global.management()}
            )
        print("Can't create a vault for something that's not actually a gauge")

    # we can create a vault for something that doesn't have a pid (aura is not the case, they are too quick)
    velo_global.createNewVaultsAndStrategiesPermissioned(
        random_gauge_not_on_convex, "poop", "poop", {"from": gov}
    )

    tx = velo_global.createNewVaultsAndStrategiesPermissioned(
        gauge, "stuff", "stuff", {"from": gov}
    )
    vault_address = tx.events["NewAutomatedVault"]["vault"]
    vault = Contract(vault_address)
    print("Vault name:", vault.name())

    print("Vault endorsed:", vault_address)
    info = tx.events["NewAutomatedVault"]

    # check that everything is setup properly for our vault
    assert vault.governance() == velo_global.address
    assert vault.management() == velo_global.management()
    assert vault.guardian() == velo_global.guardian()
    assert vault.guardian() == velo_global.guardian()
    assert vault.depositLimit() == velo_global.depositLimit()
    assert vault.rewards() == velo_global.treasury()
    assert vault.managementFee() == velo_global.managementFee()
    assert vault.performanceFee() == velo_global.performanceFee()
    print("Asserts good for our vault")

    print("Here's our new vault created event:", info, "\n")

    # curve
    curve_strat = tx.events["NewAutomatedVault"]["veloStrategy"]
    curve_strategy = StrategyVelodromeClonable.at(curve_strat)
    print("Curve strategy:", curve_strat)

    # curve
    assert vault.withdrawalQueue(0) == curve_strat
    assert vault.strategies(curve_strat)["performanceFee"] == 0
    assert curve_strategy.creditThreshold() == 5e22
    assert curve_strategy.healthCheck() == velo_global.healthCheck()
    assert curve_strategy.localkeepVELO() == velo_global.keepVELO()
    assert curve_strategy.veloVoter() == velo_global.veloVoter()
    assert curve_strategy.rewards() == velo_global.treasury()
    assert curve_strategy.strategist() == velo_global.management()
    assert curve_strategy.keeper() == velo_global.keeper()
    print("Asserts good for our curve strategy")

    # daddy needs to accept gov on all new vaults
    vault.acceptGovernance({"from": gov})
    assert vault.governance() == gov.address
    print("Gov accepted by daddy")

    # deploy a FUD vault, should have convex and curve.
    if pid != 36:
        chain.sleep(1)
        chain.mine(1)

        # no keepVELO here to hit the other side of the if statement
        velo_global.setkeepVELO(0, velo_global.veloVoter(), {"from": gov})

        tx = velo_global.createNewVaultsAndStrategiesPermissioned(
            fud_gauge,
            "FUD Vault",
            "yvCurve-FUD",
            {"from": velo_global.management()},
        )
        print("New FUD vault deployed, vault/convex/curve", tx.return_value)
        chain.sleep(1)
        chain.mine(1)

    if not tests_using_tenderly:
        # we can't deploy another curve vault because of our curve strategy
        with brownie.reverts("Voter strategy already exists"):
            tx = velo_global.createNewVaultsAndStrategiesPermissioned(
                gauge, "test2", "test2", {"from": velo_global.management()}
            )


def test_no_curve(
    StrategyConvexFactoryClonable,
    StrategyVelodromeClonable,
    strategist,
    velo_global,
    gov,
    guardian,
    token,
    health_check,
    pid,
    base_fee_oracle,
    new_registry,
    gauge,
    new_proxy,
    voter,
    whale,
    tests_using_tenderly,
    fud_gauge,
):
    # once our factory is deployed, setup the factory from gov
    registry_owner = accounts.at(new_registry.owner(), force=True)
    new_registry.setApprovedVaultsOwner(velo_global, True, {"from": registry_owner})
    new_registry.setVaultEndorsers(velo_global, True, {"from": registry_owner})

    # make sure our curve global can own vaults and endorse them
    assert new_registry.approvedVaultsOwner(velo_global)
    assert new_registry.vaultEndorsers(velo_global)
    assert velo_global.registry() == new_registry.address
    print("Our factory can endorse vaults")

    _pid = velo_global.getPid(gauge)
    assert _pid == pid
    print("\nOur pid workup works, pid:", pid)

    # update the strategy on our voter
    voter.setStrategy(new_proxy.address, {"from": gov})

    # set our factory address on the strategy proxy
    new_proxy.setFactory(velo_global.address, {"from": gov})
    print("New proxy updated, factory added to proxy")
    print("Let's deploy this vault")
    print("Factory address: ", velo_global)
    print("Gauge: ", gauge)

    # check if our current gauge has a strategy for it, but mostly just do this to update our proxy
    print(
        "Here is our strategy for the gauge (likely 0x000):",
        new_proxy.strategies(gauge),
    )

    # check if we can create this vault permissionlessly
    print(
        "Can we create this vault permissionlessly?",
        velo_global.canCreateVaultPermissionlessly(gauge),
    )

    # set curve template to zero address
    velo_global.setCurveStratImplementation(ZERO_ADDRESS, {"from": gov})

    tx = velo_global.createNewVaultsAndStrategiesPermissioned(
        gauge, "stuff", "stuff", {"from": gov}
    )
    vault_address = tx.events["NewAutomatedVault"]["vault"]
    vault = Contract(vault_address)
    print("Vault name:", vault.name())
    assert vault.withdrawalQueue(1) == ZERO_ADDRESS

    print("Vault endorsed:", vault_address)
    info = tx.events["NewAutomatedVault"]

    # check that everything is setup properly for our vault
    assert vault.governance() == velo_global.address
    assert vault.management() == velo_global.management()
    assert vault.guardian() == velo_global.guardian()
    assert vault.guardian() == velo_global.guardian()
    assert vault.depositLimit() == velo_global.depositLimit()
    assert vault.rewards() == velo_global.treasury()
    assert vault.managementFee() == velo_global.managementFee()
    assert vault.performanceFee() == velo_global.performanceFee()
    print("Asserts good for our vault")

    print("Here's our new vault created event:", info, "\n")

    # convex
    cvx_strat = tx.events["NewAutomatedVault"]["convexStrategy"]
    convex_strategy = StrategyConvexFactoryClonable.at(cvx_strat)
    print("Convex strategy:", cvx_strat)

    assert vault.withdrawalQueue(0) == cvx_strat
    assert vault.strategies(cvx_strat)["performanceFee"] == 0
    assert convex_strategy.creditThreshold() == 5e22  # 50k
    assert convex_strategy.healthCheck() == velo_global.healthCheck()
    assert (
        convex_strategy.harvestProfitMaxInUsdc() == velo_global.harvestProfitMaxInUsdc()
    )
    assert (
        convex_strategy.harvestProfitMinInUsdc() == velo_global.harvestProfitMinInUsdc()
    )
    assert convex_strategy.healthCheck() == velo_global.healthCheck()
    assert convex_strategy.localkeepVELO() == velo_global.keepVELO()
    assert convex_strategy.localKeepCVX() == velo_global.keepCVX()
    assert convex_strategy.convexVoter() == velo_global.convexVoter()
    assert convex_strategy.rewards() == velo_global.treasury()
    assert convex_strategy.strategist() == velo_global.management()
    assert convex_strategy.keeper() == velo_global.keeper()
    print("Asserts good for our convex strategy")

    # daddy needs to accept gov on all new vaults
    vault.acceptGovernance({"from": gov})
    assert vault.governance() == gov.address
    print("Gov accepted by daddy")

    # deploy a FUD vault, should have convex and curve.
    if pid != 36:
        chain.sleep(1)
        chain.mine(1)
        tx = velo_global.createNewVaultsAndStrategiesPermissioned(
            fud_gauge,
            "FUD Vault",
            "yvCurve-FUD",
            {"from": gov},
        )
        print("New FUD vault deployed, vault/convex/curve", tx.return_value)
        chain.sleep(1)
        chain.mine(1)


def test_velo_global_setters_and_views(
    gov,
    whale,
    amount,
    velo_global,
    new_registry,
    gauge,
    pid,
    token,
    fud_gauge,
    voter,
    new_proxy,
):

    # once our factory is deployed, setup the factory from gov
    registry_owner = accounts.at(new_registry.owner(), force=True)
    new_registry.setApprovedVaultsOwner(velo_global, True, {"from": registry_owner})
    new_registry.setVaultEndorsers(velo_global, True, {"from": registry_owner})

    # make sure our curve global can own vaults and endorse them
    assert new_registry.approvedVaultsOwner(velo_global)
    assert new_registry.vaultEndorsers(velo_global)
    print("Our factory can endorse vaults")

    # check our views
    print("Time to check the views")

    # this one causes our coverage tests to crash, so make it call only
    _pid = velo_global.getPid(gauge)
    assert _pid == pid
    print("PID is good")

    # trying to pull a PID for an address that doesn't have one should return max uint
    fake_pid = velo_global.getPid(gov)
    assert fake_pid == 2**256 - 1
    print("Fake gauge gives max uint")

    # check our deployed vaults
    all_vaults = velo_global.allDeployedVaults()
    print("All vaults:", all_vaults)

    length = velo_global.numVaults()
    print("Number of vaults:", length)

    # check if we can create vaults
    assert not velo_global.canCreateVaultPermissionlessly(fud_gauge)

    # this one should always be yes (SDT/ETH) as we will almost certainly never make a vault for this
    assert velo_global.canCreateVaultPermissionlessly(
        "0x60355587a8D4aa67c2E64060Ab36e566B9bCC000"
    )

    # update the strategy on our voter
    voter.setStrategy(new_proxy.address, {"from": gov})

    # this one should be no since we haven't added any gauges to our balancer proxy yet
    assert not velo_global.doesStrategyProxyHaveGauge(fud_gauge)

    # check our latest vault for FUD
    latest = velo_global.latestStandardVaultFromGauge(fud_gauge)
    print("Latest FUD vault:", latest)

    # check our setters
    with brownie.reverts():
        velo_global.setKeepCVX(69, gov, {"from": whale})
    velo_global.setKeepCVX(0, gov, {"from": gov})
    velo_global.setKeepCVX(69, gov, {"from": gov})
    assert velo_global.keepCVX() == 69
    assert velo_global.convexVoter() == gov.address
    with brownie.reverts():
        velo_global.setKeepCVX(69, ZERO_ADDRESS, {"from": gov})
    with brownie.reverts():
        velo_global.setKeepCVX(10_001, gov, {"from": gov})

    with brownie.reverts():
        velo_global.setkeepVELO(69, gov, {"from": whale})
    velo_global.setkeepVELO(0, gov, {"from": gov})
    velo_global.setkeepVELO(69, gov, {"from": gov})
    assert velo_global.keepVELO() == 69
    assert velo_global.veloVoter() == gov.address
    with brownie.reverts():
        velo_global.setkeepVELO(69, ZERO_ADDRESS, {"from": gov})
    with brownie.reverts():
        velo_global.setkeepVELO(10_001, gov, {"from": gov})

    with brownie.reverts():
        velo_global.setDepositLimit(69, {"from": whale})
    velo_global.setDepositLimit(0, {"from": gov})
    velo_global.setDepositLimit(69, {"from": velo_global.management()})
    assert velo_global.depositLimit() == 69

    with brownie.reverts():
        velo_global.setHarvestProfitMaxInUsdc(69, {"from": whale})
    velo_global.setHarvestProfitMaxInUsdc(0, {"from": gov})
    velo_global.setHarvestProfitMaxInUsdc(69, {"from": velo_global.management()})
    assert velo_global.harvestProfitMaxInUsdc() == 69

    with brownie.reverts():
        velo_global.setHarvestProfitMinInUsdc(69, {"from": whale})
    velo_global.setHarvestProfitMinInUsdc(0, {"from": gov})
    velo_global.setHarvestProfitMinInUsdc(69, {"from": velo_global.management()})
    assert velo_global.harvestProfitMinInUsdc() == 69

    with brownie.reverts():
        velo_global.setKeeper(gov, {"from": whale})
    velo_global.setKeeper(whale, {"from": gov})
    velo_global.setKeeper(gov, {"from": velo_global.management()})
    assert velo_global.keeper() == gov.address

    with brownie.reverts():
        velo_global.setHealthcheck(gov, {"from": whale})
    velo_global.setHealthcheck(whale, {"from": gov})
    velo_global.setHealthcheck(gov, {"from": velo_global.management()})
    assert velo_global.healthCheck() == gov.address

    with brownie.reverts():
        velo_global.setRegistry(gov, {"from": whale})
    velo_global.setRegistry(gov, {"from": gov})
    assert velo_global.registry() == gov.address

    with brownie.reverts():
        velo_global.setGuardian(gov, {"from": whale})
    velo_global.setGuardian(gov, {"from": gov})
    assert velo_global.guardian() == gov.address

    with brownie.reverts():
        velo_global.setConvexPoolManager(gov, {"from": whale})
    velo_global.setConvexPoolManager(gov, {"from": gov})
    assert velo_global.convexPoolManager() == gov.address

    with brownie.reverts():
        velo_global.setBooster(gov, {"from": whale})
    velo_global.setBooster(gov, {"from": gov})
    assert velo_global.booster() == gov.address

    with brownie.reverts():
        velo_global.setGovernance(gov, {"from": whale})
    velo_global.setGovernance(gov, {"from": gov})
    assert velo_global.governance() == gov.address

    with brownie.reverts():
        velo_global.setManagement(gov, {"from": whale})
    velo_global.setManagement(gov, {"from": gov})
    assert velo_global.management() == gov.address

    with brownie.reverts():
        velo_global.setGuardian(gov, {"from": whale})
    velo_global.setGuardian(gov, {"from": gov})
    assert velo_global.guardian() == gov.address

    with brownie.reverts():
        velo_global.setTreasury(gov, {"from": whale})
    velo_global.setTreasury(gov, {"from": gov})
    assert velo_global.treasury() == gov.address

    with brownie.reverts():
        velo_global.setTradeFactory(gov, {"from": whale})
    velo_global.setTradeFactory(gov, {"from": gov})
    assert velo_global.tradeFactory() == gov.address

    with brownie.reverts():
        velo_global.setBaseFeeOracle(gov, {"from": whale})
    velo_global.setBaseFeeOracle(gov, {"from": gov})
    velo_global.setBaseFeeOracle(gov, {"from": velo_global.management()})
    assert velo_global.baseFeeOracle() == gov.address

    with brownie.reverts():
        velo_global.setConvexStratImplementation(gov, {"from": whale})
    velo_global.setConvexStratImplementation(gov, {"from": gov})
    assert velo_global.convexStratImplementation() == gov.address

    with brownie.reverts():
        velo_global.setCurveStratImplementation(gov, {"from": whale})
    velo_global.setCurveStratImplementation(gov, {"from": gov})
    assert velo_global.curveStratImplementation() == gov.address

    with brownie.reverts():
        velo_global.setManagementFee(69, {"from": whale})
    velo_global.setManagementFee(69, {"from": gov})
    assert velo_global.managementFee() == 69
    with brownie.reverts():
        velo_global.setManagementFee(9999, {"from": gov})

    with brownie.reverts():
        velo_global.setPerformanceFee(69, {"from": whale})
    velo_global.setPerformanceFee(69, {"from": gov})
    assert velo_global.performanceFee() == 69
    with brownie.reverts():
        velo_global.setPerformanceFee(9999, {"from": gov})

    with brownie.reverts():
        velo_global.setOwner(gov, {"from": whale})
    velo_global.setOwner(whale, {"from": gov})
    with brownie.reverts():
        velo_global.acceptOwner({"from": gov})
    velo_global.acceptOwner({"from": whale})
    assert velo_global.owner() == whale.address
