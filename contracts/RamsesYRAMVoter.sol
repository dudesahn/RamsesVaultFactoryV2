// SPDX-License-Identifier: MIT

pragma solidity ^0.8.15;

import "IERC20.sol";
import "SafeERC20.sol";

interface VoteEscrow {
    function create_lock(uint, uint, uint) external;
    function increase_amount(uint, uint) external;
    function withdraw(uint) external;
}

contract RamsesYRAMVoter {
    using SafeERC20 for IERC20;
    address public escrow; // veContract addr
    address public token; // token to lock
    address public governance = 0x36666EC6315E9606f03fc6527E396B95bcA4D384;
    address public strategy; // StrategyProxy
    uint256 constant public tokenId = 19; // yearn's veNFT ID
    string public name;

    function initialize(
        address _veContract,
        address _tokenToLock,
        string memory _name
    ) external {
        require(escrow == address(0), "already initialized");
        require(msg.sender == governance, "!governance");

        escrow = _veContract; // 0xAAA343032aA79eE9a6897Dab03bef967c3289a06
        token = _tokenToLock; // 0xAAA6C1E32C55A7Bfa8066A6FAE9b42650F262418
        name = _name;
    }

    function createLock(uint _value, uint _unlockTime) external {
        require(msg.sender == strategy || msg.sender == governance, "!authorized");
        IERC20(token).safeApprove(escrow, 0);
        IERC20(token).safeApprove(escrow, _value);
        VoteEscrow(escrow).create_lock(_value, _unlockTime);
    }
    
    function increaseAmount(uint _value) external {
        require(msg.sender == strategy || msg.sender == governance, "!authorized");
        IERC20(token).safeApprove(escrow, 0);
        IERC20(token).safeApprove(escrow, _value);
        VoteEscrow(escrow).increase_amount(tokenId, _value);
    }
    
    function release() external {
        require(msg.sender == strategy || msg.sender == governance, "!authorized");
        VoteEscrow(escrow).withdraw(tokenId);
    }
    
    function setStrategy(address _strategy) external {
        require(msg.sender == governance, "!governance");
        strategy = _strategy;
    }

    function setGovernance(address _governance) external {
        require(msg.sender == governance, "!governance");
        governance = _governance;
    }
    
    function execute(address payable to, uint value, bytes calldata data) external returns (bool, bytes memory) {
        require(msg.sender == strategy || msg.sender == governance, "!governance");
        (bool success, bytes memory result) = to.call{value:value}(data);
        
        return (success, result);
    }

    receive() external payable {}
}